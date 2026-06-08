"""DSP analysis of captured synth audio.

Input: a mono 16-bit WAV (44100 Hz) produced by the bridge AUDIO_RECORD
command (which taps POKEY's mixed output). These routines turn raw PCM into
the acoustic facts the scenarios assert on:

  pitch       -> fundamental frequency (autocorrelation, sub-sample refined)
  pitch_track -> framewise pitch over time (for vibrato / glide / arp)
  spectrum    -> magnitude spectrum + harmonic descriptors (timbre/waveform id)
  envelope    -> RMS amplitude over time (for ADSR shape)
  adsr        -> attack/decay/sustain/release segmentation of the envelope
  modulation  -> rate+depth of a periodic wobble in a track (LFO/vibrato/tremolo)
  beat_freq   -> amplitude beat frequency (detune / two close tones)
  is_silent / rms / peak

Everything is numpy/scipy; no playback. A WAV with N channels is downmixed.
"""
import wave
import numpy as np


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
class Clip:
    """A loaded mono audio clip: float32 samples in [-1, 1] @ sr Hz."""
    def __init__(self, samples, sr):
        self.x = np.asarray(samples, dtype=np.float64)
        self.sr = sr

    @property
    def n(self):
        return len(self.x)

    @property
    def duration(self):
        return self.n / self.sr if self.sr else 0.0

    def slice_t(self, t0, t1):
        i0 = max(0, int(t0 * self.sr))
        i1 = min(self.n, int(t1 * self.sr))
        return Clip(self.x[i0:i1], self.sr)

    def trim_silence(self, thresh=2e-3):
        """Drop leading/trailing samples below an RMS-ish amplitude threshold."""
        mask = np.abs(self.x) > thresh
        if not mask.any():
            return Clip(self.x[:0], self.sr)
        i0, i1 = np.argmax(mask), len(mask) - np.argmax(mask[::-1])
        return Clip(self.x[i0:i1], self.sr)


def load_wav(path):
    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        nch = w.getnchannels()
        sw = w.getsampwidth()
        frames = w.readframes(w.getnframes())
    if sw == 2:
        data = np.frombuffer(frames, dtype="<i2").astype(np.float64) / 32768.0
    elif sw == 1:
        data = (np.frombuffer(frames, dtype=np.uint8).astype(np.float64) - 128) / 128.0
    elif sw == 4:
        data = np.frombuffer(frames, dtype="<i4").astype(np.float64) / 2147483648.0
    else:
        raise ValueError(f"unsupported sample width {sw}")
    if nch > 1:
        data = data.reshape(-1, nch).mean(axis=1)
    return Clip(data, sr)


# ---------------------------------------------------------------------------
# Amplitude
# ---------------------------------------------------------------------------
def rms(clip):
    return float(np.sqrt(np.mean(clip.x ** 2))) if clip.n else 0.0


def peak(clip):
    return float(np.max(np.abs(clip.x))) if clip.n else 0.0


def is_silent(clip, thresh=1.5e-3):
    """True if the clip carries no audible signal (RMS below threshold)."""
    return rms(clip) < thresh


def envelope(clip, hop_ms=2.0, win_ms=8.0):
    """Framewise RMS envelope. Returns (times[s], rms[]) arrays."""
    hop = max(1, int(clip.sr * hop_ms / 1000))
    win = max(hop, int(clip.sr * win_ms / 1000))
    if clip.n < win:
        return np.array([0.0]), np.array([rms(clip)])
    starts = np.arange(0, clip.n - win, hop)
    env = np.empty(len(starts))
    for i, s in enumerate(starts):
        seg = clip.x[s:s + win]
        env[i] = np.sqrt(np.mean(seg * seg))
    t = (starts + win / 2) / clip.sr
    return t, env


# ---------------------------------------------------------------------------
# Pitch
# ---------------------------------------------------------------------------
def pitch(clip, fmin=40.0, fmax=8000.0):
    """Fundamental frequency via autocorrelation with parabolic refinement.
    Returns 0.0 if no clear periodicity (e.g. noise / silence)."""
    x = clip.x
    if len(x) < 64 or rms(clip) < 1e-4:
        return 0.0
    x = x - np.mean(x)
    # window to reduce edge effects
    x = x * np.hanning(len(x))
    # FFT-based autocorrelation (O(n log n); np.correlate 'full' is O(n^2)
    # and far too slow for the many clips the harness analyses).
    n = len(x)
    nfft = 1 << int(np.ceil(np.log2(2 * n)))
    X = np.fft.rfft(x, nfft)
    corr = np.fft.irfft(X * np.conj(X), nfft)[:n]
    if corr[0] <= 0:
        return 0.0
    lag_min = max(1, int(clip.sr / fmax))
    lag_max = min(len(corr) - 2, int(clip.sr / fmin))
    if lag_max <= lag_min:
        return 0.0
    # Skip the central lobe: autocorr near lag 0 is always high (the signal
    # barely shifted), which would make argmax pick a tiny lag = bogus high
    # pitch. Advance past the first descent into negative correlation, then
    # take the strongest peak after it (the true period gives the FIRST and
    # largest peak under the windowed-autocorr envelope, beating subharmonics).
    lobe_end = lag_min
    neg = np.where(corr[lag_min:lag_max] < 0)[0]
    if len(neg):
        lobe_end = max(lag_min, lag_min + int(neg[0]))
    search_lo = max(lag_min, lobe_end)
    if search_lo >= lag_max:
        return 0.0
    region = corr[search_lo:lag_max]
    best = float(np.max(region))
    # require the peak to be a real periodicity, not just decaying autocorr
    if best < 0.2 * corr[0]:
        return 0.0
    # Prefer the SMALLEST lag whose correlation is within 90% of the best peak
    # and is a local maximum. This rejects sub-harmonic (octave-too-low) errors
    # where a multiple of the true period also correlates strongly.
    thresh = 0.9 * best
    peak_lag = search_lo + int(np.argmax(region))   # fallback
    for i in range(1, len(region) - 1):
        if region[i] >= thresh and region[i] >= region[i - 1] and region[i] >= region[i + 1]:
            peak_lag = search_lo + i
            break
    # parabolic interpolation around the peak for sub-sample accuracy
    a, b, c = corr[peak_lag - 1], corr[peak_lag], corr[peak_lag + 1]
    denom = (a - 2 * b + c)
    delta = 0.5 * (a - c) / denom if denom != 0 else 0.0
    # a valid parabolic refinement is within +/-0.5 of the integer peak;
    # clamp so a near-flat peak can't blow the estimate up.
    delta = max(-0.5, min(0.5, delta))
    return clip.sr / (peak_lag + delta)


def pitch_track(clip, hop_ms=10.0, win_ms=40.0, fmin=40.0, fmax=8000.0):
    """Framewise pitch. Returns (times[s], freqs[Hz]); 0.0 where unvoiced."""
    hop = max(1, int(clip.sr * hop_ms / 1000))
    win = max(hop, int(clip.sr * win_ms / 1000))
    if clip.n < win:
        return np.array([0.0]), np.array([pitch(clip, fmin, fmax)])
    starts = np.arange(0, clip.n - win, hop)
    f = np.empty(len(starts))
    for i, s in enumerate(starts):
        f[i] = pitch(Clip(clip.x[s:s + win], clip.sr), fmin, fmax)
    t = (starts + win / 2) / clip.sr
    return t, f


def median_pitch(clip, fmin=40.0, fmax=8000.0):
    """Robust single pitch estimate over the voiced part of a clip."""
    _, f = pitch_track(clip, fmin=fmin, fmax=fmax)
    voiced = f[f > 0]
    return float(np.median(voiced)) if len(voiced) else 0.0


def clean_track(t, f):
    """Make a pitch track suitable for modulation analysis: keep the uniform
    time grid but replace unvoiced (0) frames and gross octave-jump outliers
    by interpolation from the voiced median. Returns (t, f_clean)."""
    f = np.asarray(f, dtype=np.float64).copy()
    voiced = f > 0
    if voiced.sum() < 4:
        return t, f
    med = np.median(f[voiced])
    # outlier = >50% away from the median (octave errors etc.)
    good = voiced & (np.abs(f - med) < 0.5 * med)
    if good.sum() < 4:
        good = voiced
    idx = np.arange(len(f))
    f[~good] = np.interp(idx[~good], idx[good], f[good])
    return t, f


def vibrato(clip, fmin=40.0, fmax=8000.0):
    """Detect periodic pitch modulation (LFO/vibrato). Returns the modulation
    dict (rate_hz, depth in Hz, mean carrier Hz, present)."""
    t, f = pitch_track(clip, hop_ms=5.0, win_ms=25.0, fmin=fmin, fmax=fmax)
    t, f = clean_track(t, f)
    return modulation(t, f)


# ---------------------------------------------------------------------------
# Spectrum / timbre
# ---------------------------------------------------------------------------
def spectrum(clip):
    """Magnitude spectrum. Returns (freqs[Hz], mag[]) (single-sided)."""
    x = clip.x - np.mean(clip.x)
    if len(x) < 8:
        return np.array([0.0]), np.array([0.0])
    x = x * np.hanning(len(x))
    spec = np.abs(np.fft.rfft(x))
    freqs = np.fft.rfftfreq(len(x), 1.0 / clip.sr)
    return freqs, spec


def spectral_features(clip):
    """Timbre descriptors for waveform identification:
      centroid   - spectral centre of mass (Hz); noise/buzz push it up
      flatness   - geometric/arithmetic mean ratio (0 tonal .. 1 noisy)
      rolloff85  - freq below which 85% of energy sits (Hz)
      odd_even   - energy ratio of odd vs even harmonics of the fundamental
                   (square waves are odd-dominant); None if no clear pitch
    """
    freqs, mag = spectrum(clip)
    p = mag ** 2
    tot = np.sum(p)
    if tot <= 0:
        return dict(centroid=0.0, flatness=1.0, rolloff85=0.0, odd_even=None)
    centroid = float(np.sum(freqs * p) / tot)
    gm = np.exp(np.mean(np.log(mag + 1e-12)))
    am = np.mean(mag + 1e-12)
    flatness = float(gm / am)
    csum = np.cumsum(p)
    rolloff = float(freqs[np.searchsorted(csum, 0.85 * tot)])

    odd_even = None
    f0 = median_pitch(clip)
    if f0 > 0:
        def harm_energy(k):
            fc = k * f0
            lo = np.searchsorted(freqs, fc - f0 * 0.3)
            hi = np.searchsorted(freqs, fc + f0 * 0.3)
            return float(np.sum(p[lo:hi]))
        odd = sum(harm_energy(k) for k in (1, 3, 5, 7))
        even = sum(harm_energy(k) for k in (2, 4, 6, 8))
        odd_even = odd / (even + 1e-9)
    return dict(centroid=centroid, flatness=flatness, rolloff85=rolloff, odd_even=odd_even)


# ---------------------------------------------------------------------------
# ADSR segmentation of an amplitude envelope
# ---------------------------------------------------------------------------
def adsr(clip, hop_ms=2.0):
    """Extract ADSR-ish features from the amplitude envelope.
    Returns dict: attack_s, peak, decay_s, sustain, release_s, total_s."""
    t, env = envelope(clip, hop_ms=hop_ms)
    if len(env) < 3 or env.max() <= 0:
        return dict(attack_s=0.0, peak=0.0, decay_s=0.0, sustain=0.0,
                    release_s=0.0, total_s=clip.duration)
    pk = float(env.max())
    pk_i = int(np.argmax(env))
    # attack: start (first cross 10% of peak) to peak
    above = np.where(env > 0.1 * pk)[0]
    start_i = above[0] if len(above) else 0
    attack_s = float(t[pk_i] - t[start_i])
    # release: from last time above 10% of peak to end
    end_i = above[-1] if len(above) else len(env) - 1
    release_s = float(t[-1] - t[end_i])
    # sustain level: median of the MIDDLE of the post-peak plateau, excluding
    # the decay ramp right after the peak and the release ramp at the end, so
    # neither slope drags the estimate.
    lo = pk_i + max(1, (end_i - pk_i) // 4)
    hi = end_i - max(1, (end_i - pk_i) // 8)
    plateau = env[lo:hi] if hi > lo else env[pk_i:max(pk_i + 1, end_i)]
    sustain = float(np.median(plateau)) if len(plateau) else pk
    # decay: peak down to within 15% of sustain
    decay_s = 0.0
    if sustain < pk:
        thr = sustain + 0.15 * (pk - sustain)
        dec = np.where(env[pk_i:] <= thr)[0]
        if len(dec):
            decay_s = float(t[pk_i + dec[0]] - t[pk_i])
    return dict(attack_s=attack_s, peak=pk, decay_s=decay_s, sustain=sustain,
                release_s=release_s, total_s=clip.duration)


# ---------------------------------------------------------------------------
# Modulation (LFO / vibrato / tremolo) in a time series
# ---------------------------------------------------------------------------
def modulation(t, series, rate_band=None):
    """Rate (Hz) and depth of a periodic oscillation in `series` (sampled at
    times `t`). Depth = half the peak-to-peak after detrending; rate from the
    dominant FFT bin. `rate_band=(lo,hi)` restricts the dominant-bin search to
    that frequency range (e.g. real vibrato/beats are slow, a few Hz).
    Returns dict(rate_hz, depth, mean, present)."""
    s = np.asarray(series, dtype=np.float64)
    s = s[np.isfinite(s)]
    if len(s) < 8:
        return dict(rate_hz=0.0, depth=0.0, mean=float(np.mean(s) if len(s) else 0), present=False)
    dt = float(np.median(np.diff(t[:len(s)]))) if len(t) > 1 else 1.0
    mean = float(np.mean(s))
    ac = s - mean
    depth = float((np.percentile(ac, 95) - np.percentile(ac, 5)) / 2.0)
    # dominant frequency within the band (default: everything but DC)
    win = ac * np.hanning(len(ac))
    spec = np.abs(np.fft.rfft(win))
    freqs = np.fft.rfftfreq(len(ac), dt)
    spec[0] = 0.0
    if rate_band is not None:
        lo, hi = rate_band
        spec = spec.copy()
        spec[(freqs < lo) | (freqs > hi)] = 0.0
    k = int(np.argmax(spec))
    rate = float(freqs[k])
    # "present" if the oscillation is a real periodic swing: a meaningful
    # fraction of the series level (rejects analysis jitter on a flat signal)
    # AND a dominant spectral bin above the series' own noise floor.
    rel = depth / (abs(mean) + 1e-9)
    present = (rel > 1e-3 and depth > 1e-4 and rate > 0
               and spec[k] > 4.0 * np.median(spec + 1e-12))
    return dict(rate_hz=rate, depth=depth, mean=mean, present=present)


def spectral_peaks(clip, count=8, min_hz=40.0, min_rel=0.08):
    """Prominent spectral peaks as (hz, mag), strongest first. Used to confirm
    several simultaneous tones (a real chord) are present in the mix."""
    freqs, mag = spectrum(clip)
    if len(mag) < 3:
        return []
    thresh = min_rel * float(mag.max())
    peaks = []
    for i in range(1, len(mag) - 1):
        if freqs[i] < min_hz:
            continue
        if mag[i] >= mag[i - 1] and mag[i] >= mag[i + 1] and mag[i] >= thresh:
            peaks.append((float(freqs[i]), float(mag[i])))
    peaks.sort(key=lambda p: -p[1])
    return peaks[:count]


def has_tone_at(clip, hz, tol_frac=0.04, min_rel=0.08):
    """True if a spectral peak sits within tol_frac of `hz` (a tone at that
    frequency is audibly present in the mix)."""
    for f, _ in spectral_peaks(clip, count=16, min_rel=min_rel):
        if abs(f - hz) <= tol_frac * hz:
            return True
    return False


def distinct_pitches(clip, hop_ms=10.0, win_ms=40.0, fmin=40.0, fmax=8000.0):
    """Set of distinct nearest-ET note names heard over time (voiced frames).
    Used to confirm an arpeggio/glide passes through several notes. Pass a
    tighter fmin/fmax to suppress octave-error outliers on busy signals."""
    from . import notes
    t, f = pitch_track(clip, hop_ms=hop_ms, win_ms=win_ms, fmin=fmin, fmax=fmax)
    names = {}
    for fr in f:
        if fr > 0:
            n = notes.nearest_et(fr)[0]
            names[n] = names.get(n, 0) + 1
    # keep notes that occupy a meaningful share of frames (drop transients)
    voiced = sum(names.values()) or 1
    return {n for n, c in names.items() if c / voiced >= 0.1}


def onsets(clip, hop_ms=4.0, win_ms=20.0, hi_frac=0.40, lo_frac=0.18, min_gap_ms=60.0):
    """Note-onset times (s) from the amplitude envelope, with HYSTERESIS: fire
    when the (smoothed) envelope rises above hi_frac*peak, and only re-arm after
    it falls below lo_frac*peak. The wide window + hysteresis reject the RMS
    ripple of a POKEY square wave, so only true note boundaries register.
    Used to measure rhythm/tempo from the rendered audio."""
    t, env = envelope(clip, hop_ms=hop_ms, win_ms=win_ms)
    if len(env) < 2 or env.max() <= 0:
        return []
    pk = float(env.max())
    hi, lo = hi_frac * pk, lo_frac * pk
    out, armed, last = [], True, -1e9
    for i in range(len(env)):
        if armed and env[i] >= hi and (t[i] - last) * 1000.0 >= min_gap_ms:
            out.append(float(t[i])); last = t[i]; armed = False
        elif not armed and env[i] < lo:
            armed = True
    return out


def inter_onset_intervals(clip, **kw):
    """Gaps (s) between successive detected onsets — the note rhythm."""
    on = onsets(clip, **kw)
    return [on[i + 1] - on[i] for i in range(len(on) - 1)]


def fall_time(clip, frac=0.3, hop_ms=2.0):
    """Time (s) from the envelope peak to when it first falls below frac*peak.
    Used to measure release/decay timing directly (a slower release -> longer
    fall). Returns the clip duration if it never falls that far."""
    t, env = envelope(clip, hop_ms=hop_ms)
    if len(env) < 2 or env.max() <= 0:
        return 0.0
    pk_i = int(np.argmax(env))
    pk = env[pk_i]
    below = np.where(env[pk_i:] < frac * pk)[0]
    return float(t[pk_i + below[0]] - t[pk_i]) if len(below) else float(t[-1] - t[pk_i])


def beat_freq(clip, band=(0.5, 30.0)):
    """Amplitude beat frequency (Hz) from the envelope — detects detuned
    voices beating against each other. Restricted to a slow beat band (real
    beats are a few Hz, not the kHz tone itself). 0 if no steady beat."""
    t, env = envelope(clip, hop_ms=4.0, win_ms=12.0)
    m = modulation(t, env, rate_band=band)
    return m["rate_hz"] if m["present"] else 0.0
