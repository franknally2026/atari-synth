# Atari POKEY Synth — Podręcznik użytkownika

*Język: [English](USER_GUIDE_EN.md) · **Polski***

Witaj! To praktyczny przewodnik po *graniu* na syntezatorze. Przeprowadzi Cię od
pierwszego dźwięku aż po nagranie całej sekwencji z perkusją i zapisanie własnych
brzmień. Nie potrzebujesz znać asemblera ani teorii — po prostu usiądź przy
klawiaturze i wykonuj kolejne kroki.

---

## Spis treści

- [1. Uruchamianie](#1-uruchamianie)
- [2. Co widać na ekranie](#2-co-widać-na-ekranie)
- [3. Granie pierwszych dźwięków](#3-granie-pierwszych-dźwięków)
- [4. Zmiana brzmienia joystickiem](#4-zmiana-brzmienia-joystickiem)
- [5. Samouczki](#5-samouczki)
  - [5.1 Kształtowanie brzmienia (obwiednia)](#51-kształtowanie-brzmienia-obwiednia)
  - [5.2 Dodaj vibrato (LFO)](#52-dodaj-vibrato-lfo)
  - [5.3 Pogrub brzmienie (detune)](#53-pogrub-brzmienie-detune)
  - [5.4 Nastrój instrument (tryb 16-bit)](#54-nastrój-instrument-tryb-16-bit)
  - [5.5 Solo z glissandem (portamento)](#55-solo-z-glissandem-portamento)
  - [5.6 Arpeggia](#56-arpeggia)
  - [5.7 Rozjaśnij brzmienie (filtr górnoprzepustowy)](#57-rozjaśnij-brzmienie-filtr-górnoprzepustowy)
  - [5.8 Dodaj perkusję](#58-dodaj-perkusję)
  - [5.9 Nagraj sekwencję (sekwencer)](#59-nagraj-sekwencję-sekwencer)
  - [5.10 Dodaj ścieżkę perkusji do sekwencji](#510-dodaj-ścieżkę-perkusji-do-sekwencji)
  - [5.11 Zapisz i przywołaj brzmienia (presety)](#511-zapisz-i-przywołaj-brzmienia-presety)
- [6. Ściąga ze sterowaniem](#6-ściąga-ze-sterowaniem)
- [7. Rozwiązywanie problemów / FAQ](#7-rozwiązywanie-problemów--faq)
- [8. Wskazówki](#8-wskazówki)

---

## 1. Uruchamianie

Wczytaj `synth.xex` na Atari 8-bit w wersji **PAL** (albo `./build.sh run`, żeby
uruchomić emulator). Do panelu sterowania potrzebny będzie **joystick w porcie 1**.

Po uruchomieniu zobaczysz panel sterowania u góry ekranu i narysowaną klawiaturę
pianina na dole. To wszystko — możesz grać.

---

## 2. Co widać na ekranie

- **Panel (góra):** rzędy **gałek** i przełączników — to są regulatory brzmienia.
  Tylko przy jednym regulatorze naraz świeci się **znacznik `>`**; to właśnie nim
  steruje joystick.
- **Nazwa dźwięku (prawy górny róg):** pokazuje aktualnie grany dźwięk, np. `C 4`.
- **Wskaźniki VU:** paseczki, które zapalają się, pokazując, który z czterech
  głosów gra.
- **Klawiatura pianina (dół):** naciśnięty klawisz się podświetla.

Panel ma **trzy strony**. Strony nie wybiera się bezpośrednio — gdy przesuwasz
zaznaczenie poza koniec strony (w górę lub w dół), automatycznie przeskakuje ono
na następną.

- **Strona 1** — główne regulatory brzmienia (fala, głośność, oktawa, obwiednia,
  detune, zegar, LFO, arpeggiator).
- **Strona 2** — sekwencer (tempo, tryb arpeggia, portamento, perkusja) plus
  siatka kroków.
- **Strona 3** — filtr i presety.

---

## 3. Granie pierwszych dźwięków

Klawiszy liter i cyfr używa się jak klawiatury jednooktawowego pianina:

```
czarne klawisze:   2   3       5   6   7       9   0
białe klawisze:  Q   W   E   R   T   Y   U   I   O   P
gra:             C   D   E   F   G   A   B   C   D   E
```

- **Górny rząd białych** `Q W E R T Y U I O P` gra dźwięki naturalne.
- **Rząd cyfr** `2 3 5 6 7 9 0` gra krzyżyki (czarne klawisze).
- `1` to klawisz **perkusji** (więcej dalej). `4` i `8` nic nie robią — tak jak w
  prawdziwym pianinie, nie ma tam czarnego klawisza.

Naciśnij kilka klawiszy. Powinieneś usłyszeć dźwięki, zobaczyć podświetlony
klawisz i nazwę dźwięku w prawym górnym rogu.

**Granie akordów:** Atari rozpoznaje tylko jeden klawisz naraz, więc żeby
przytrzymać akord, albo zagraj dźwięki szybko po kolei (przez chwilę wybrzmiewają
razem), albo przytrzymaj klawisz konsoli **OPTION** jako pedał sustain — wtedy
każdy zagrany dźwięk wybrzmiewa, dopóki nie puścisz OPTION.

---

## 4. Zmiana brzmienia joystickiem

Wszystko na panelu zmienia się tak samo:

1. **Wychyl joystick w górę lub w dół**, żeby przesunąć znacznik `>` na regulator,
   który chcesz zmienić. (Wychylaj dalej w tę samą stronę, by przewijać przez
   wszystkie regulatory; lista zawija się, a strona przeskakuje automatycznie.)
2. **Wychyl w lewo lub w prawo**, żeby ten regulator zmniejszyć lub zwiększyć.
   Przytrzymaj — działa autopowtarzanie.

To cały interfejs. Graj dźwięk podczas kręcenia gałką, żeby słyszeć zmianę na
żywo. Spróbuj teraz: przesuń znacznik na **VOLUME** i wychylaj w lewo/prawo — dźwięk
robi się cichszy i głośniejszy.

> W całym przewodniku „**wybierz X**” oznacza *wychylaj w górę/dół, aż znacznik `>`
> będzie przy X*, a „**zwiększ/zmniejsz X**” oznacza *wychylaj w prawo/lewo*.

---

## 5. Samouczki

Każdy samouczek jest niezależny. Graj dźwięk (albo przytrzymaj go) podczas
wprowadzania zmian, żeby je słyszeć.

### 5.1 Kształtowanie brzmienia (obwiednia)

**Obwiednia** decyduje, jak dźwięk narasta i wygasa: **ATTACK** (jak szybko się
pojawia), **DECAY** (jak szybko opada do poziomu podtrzymania), **SUSTAIN**
(poziom utrzymywany, dopóki trzymasz klawisz), **RELEASE** (jak szybko wygasa po
puszczeniu klawisza).

**Zrób organy (od razu brzmi, trzyma się, szybko gaśnie):**
1. Wybierz **ATTACK** i ustaw na **0**.
2. Wybierz **SUSTAIN** i ustaw **wysoko** (12–15).
3. Wybierz **RELEASE** i ustaw na **2–3**.
4. Przytrzymaj klawisz — od razu jest głośny, trzyma się równo i szybko cichnie
   po puszczeniu.

**Zrób miękki pad (powolne narastanie):**
1. **ATTACK** zwiększ do **6–8** — dźwięki będą się powoli pojawiać.
2. **RELEASE** zwiększ do **8+** — będą też powoli wygasać.
3. Przytrzymaj OPTION i zagraj kilka dźwięków — powolny, narastający akord.

**Zrób szarpnięcie (gaśnie nawet przy trzymanym klawiszu):**
1. **ATTACK 0**, **DECAY 4**, **SUSTAIN 0**.
2. Przytrzymaj klawisz — dźwięk szarpie i sam zanika.

### 5.2 Dodaj vibrato (LFO)

**LFO** kołysze wysokością dźwięku w górę i w dół, dając vibrato.

1. Wybierz **LFO DEPTH** i zwiększ do około **6**. Zagraj dźwięk — usłyszysz
   kołysanie wysokości.
2. Wybierz **LFO RATE** i wyreguluj, jak *szybko* się kołysze.
3. Ustaw **LFO DEPTH** z powrotem na **0**, by wyłączyć vibrato.

Mała głębia + średnie tempo = delikatne migotanie. Duża głębia + wolne tempo =
głębokie, powolne zaginanie wysokości.

### 5.3 Pogrub brzmienie (detune)

**DETUNE** lekko rozstraja cztery głosy względem siebie, tak że dudnią ze sobą,
dając gęste brzmienie z efektem chorus.

1. Wybierz **DETUNE** i zwiększ do **8–12**.
2. Zagraj kilka dźwięków szybko po sobie (żeby grał więcej niż jeden głos) —
   usłyszysz migotanie/dudnienie. Niższe dźwięki dają ładny, powolny chorus.
3. Ustaw DETUNE na **0**, by mieć czysty strój.

### 5.4 Nastrój instrument (tryb 16-bit)

Domyślnie (zegar NORMAL) syntezator gra w wysokim rejestrze, a wysokie dźwięki są
nieco rozstrojone. Aby uzyskać dokładny, czysty strój na całej klawiaturze:

1. Wybierz **CLOCK**.
2. Ustaw na **16-BIT**.

Teraz klawiatura jest nastrojona do stroju koncertowego i utrzymuje czysty strój
nawet w wysokim rejestrze. (Kompromis: tryb 16-bit gra **dwa dźwięki naraz**
zamiast czterech.) Wróć do **NORMAL**, by mieć jaśniejsze, 4-głosowe brzmienie
domyślne.

### 5.5 Solo z glissandem (portamento)

**Portamento** sprawia, że każdy nowy dźwięk *zsuwa się* z poprzedniego.

1. Wybierz **PORTA** (jest na stronie 2 — przewiń w dół poza regulatory strony 1).
2. Zwiększ do **6–10**.
3. Zagraj dźwięk, potem kolejny — wysokość płynnie się przesuwa. (Przy włączonym
   portamento syntezator gra jeden dźwięk naraz, jak klasyczne mono-solo.)
4. Ustaw PORTA na **0**, by wrócić do zwykłych, natychmiastowych dźwięków.

### 5.6 Arpeggia

Przytrzymaj jeden klawisz i pozwól syntezatorowi grać powtarzający się wzór
akordu.

1. Wybierz **ARP** (strona 1) i zwiększ do około **8**.
2. **Przytrzymaj** klawisz — usłyszysz 4-dźwiękowe arpeggio zbudowane na tym
   dźwięku. Wyższe ARP = szybciej.
3. Wybierz **ARP MODE** (strona 2) i wypróbuj wzory: **UP**, **DOWN**, **MINOR**,
   **OCT** (skok o oktawę).
4. Ustaw ARP na **0**, by grać normalnie.

### 5.7 Rozjaśnij brzmienie (filtr górnoprzepustowy)

**HP FILTER** usuwa niskie częstotliwości, ścieniając i rozjaśniając brzmienie.

1. Wybierz **HP FILTER** (strona 3 — przewiń w dół poza portamento/perkusję).
2. Zwiększaj — brzmienie staje się coraz cieńsze i jaśniejsze.
3. Ustaw na **0**, by wyłączyć filtr.

(Filtr obejmuje główny głos i działa w trybach NORMAL oraz 15 kHz.)

### 5.8 Dodaj perkusję

Jest osobny głos perkusyjny. Najpierw go **włącz**, potem **wyzwól**.

1. Wybierz **DRUM** (strona 2) i zwiększ do około **8**. To włącza perkusję i
   ustawia, jak długo wybrzmiewa każde uderzenie. (Samo w sobie nic jeszcze nie
   robi — trzeba je *wyzwolić*.)
2. **Naciskaj klawisz `1`** — przy każdym naciśnięciu dostajesz uderzenie
   perkusji. Przy wyżej ustawionym DRUM uderzenia wybrzmiewają dłużej; nisko —
   są krótkie i suche.

**Chcesz automatyczny rytm?**
3. Wybierz **DRUMBEAT** (strona 3) i zwiększ. Teraz perkusja pulsuje sama, w
   tempie regulatora **TEMPO**. Wyższy DRUMBEAT = częstsze uderzenia. Ustaw
   DRUMBEAT na **0**, by zatrzymać automatyczny rytm.

> Jeśli zwiększysz DRUM (albo DRUMBEAT) i nic nie słyszysz: pamiętaj, że **DRUM
> musi być powyżej 0**, żeby w ogóle włączyć perkusję, i nadal potrzebujesz
> wyzwalacza — naciśnij `1`, albo zwiększ DRUMBEAT, albo wpisz to do sekwencera
> (następna sekcja).

### 5.9 Nagraj sekwencję (sekwencer)

Sekwencer nagrywa 16-krokową pętlę. Sterują nim klawisze konsoli:

- **START** = odtwarzanie / stop
- **SELECT** = nagrywanie

Przewiń na **stronę 2** (wybierz TEMPO/ARP MODE/PORTA/DRUM), żeby zobaczyć siatkę
kroków.

**Najprostszy sposób — zagraj na żywo (nagrywanie w czasie rzeczywistym):**
1. Naciśnij raz **SELECT**. To czyści sekwencję i zaczyna nagrywanie w tempie.
2. **Graj dźwięki** na klawiaturze — są zapisywane zgodnie z rytmem, gdy grasz.
3. Naciśnij **SELECT** ponownie, by zatrzymać nagrywanie. Pętla gra dalej.
4. Naciśnij **START**, by zatrzymać odtwarzanie (i ponownie, by wznowić). Dostrój
   **TEMPO** wedle uznania.

Granie kolejnych dźwięków podczas nagrywania **dogrywa** je do sekwencji
(overdub), więc możesz budować ją warstwami.

**Sposób precyzyjny — krok po kroku (wpisywanie krokowe):**
1. Naciśnij **SELECT**, by uzbroić nagrywanie, a potem **START**, by *zatrzymać
   zegar*.
2. Teraz każdy naciśnięty klawisz wypełnia **jeden krok** i przechodzi do
   następnego. Buduj melodię dźwięk po dźwięku.
3. Naciśnij **START**, by odtworzyć sekwencję.

### 5.10 Dodaj ścieżkę perkusji do sekwencji

Gdy masz już nagraną melodię, dograj perkusję do tej samej sekwencji:

1. Przy nagrywającym sekwencerze (w czasie rzeczywistym, z 5.9) upewnij się, że
   **DRUM** jest zwiększony (strona 2).
2. **Naciskaj klawisz `1` na tych uderzeniach, na których chcesz mieć
   perkusję.** Staną się uderzeniami perkusji w sekwencji.
3. Zatrzymaj nagrywanie (**SELECT**). Odtwórz (**START**) — melodia i perkusja
   grają razem z jednej pętli.

### 5.11 Zapisz i przywołaj brzmienia (presety)

Są **4 sloty presetów**, wstępnie wypełnione brzmieniami startowymi (INIT, PAD,
LEAD, ARP).

**Wczytaj preset:**
1. Wybierz **PRESET** (strona 3).
2. Kręć w lewo/prawo, by wybrać slot (0–3) — brzmienie zmienia się w chwili, gdy
   trafisz na slot. Wypróbuj wszystkie.

**Zapisz własne brzmienie do slotu:**
1. Ustaw brzmienie, które Ci się podoba (dowolnymi regulatorami powyżej).
2. Wybierz **PRESET** i wskaż slot, który chcesz nadpisać.
3. **Naciśnij przycisk fire (ogień) na joysticku** — bieżące brzmienie zostaje
   zapisane w tym slocie.

Teraz możesz w każdej chwili do niego wrócić, wybierając ten slot.

---

## 6. Ściąga ze sterowaniem

**Klawiatura**
- `Q W E R T Y U I O P` — białe dźwięki (C D E F G A B C D E)
- `2 3 5 6 7 9 0` — czarne dźwięki (krzyżyki)
- `1` — uderzenie perkusji (wymaga DRUM > 0)

**Joystick (port 1)**
- Góra / Dół — przesuń znacznik `>` (wybierz regulator; strony przeskakują
  automatycznie)
- Lewo / Prawo — zmniejsz / zwiększ wybrany regulator
- Fire (ogień) — zapisz bieżące brzmienie do wybranego slotu presetu (gdy
  zaznaczony jest PRESET)

**Klawisze konsoli**
- START — odtwarzanie / stop sekwencera
- SELECT — nagrywanie sekwencera (w czasie rzeczywistym; po uzbrojeniu naciśnij
  START, by wpisywać krokowo)
- OPTION — pedał sustain (przytrzymaj, by dźwięki wybrzmiewały)

**Trzy strony panelu** (dostępne przez przewijanie w górę/dół)
- Strona 1: WAVEFORM, VOLUME, OCTAVE, ATTACK, DECAY, DETUNE, SUSTAIN, RELEASE,
  CLOCK, LFO RATE, LFO DEPTH, ARP
- Strona 2: TEMPO, ARP MODE, PORTA, DRUM (+ siatka kroków)
- Strona 3: HP FILTER, PRESET, DRUMBEAT

---

## 7. Rozwiązywanie problemów / FAQ

**Pokręciłem gałką (DRUM / DRUMBEAT), ale nic nie słyszę.**
Perkusja wymaga **DRUM powyżej 0**, żeby była włączona, *oraz* wyzwalacza:
naciśnij klawisz `1`, zwiększ **DRUMBEAT**, by mieć automatyczny rytm, albo wpisz
ją do sekwencera. Sam DRUM ustala tylko, jak brzmi uderzenie.

**Nie mogę zagrać akordu, trzymając kilka klawiszy.**
Klawiatura Atari rozpoznaje tylko jeden klawisz naraz. Graj dźwięki szybko po
sobie albo przytrzymaj **OPTION** (pedał sustain) i je naciskaj — będą
wybrzmiewać razem.

**Dźwięki brzmią za wysoko / trochę fałszują.**
To domyślny zegar NORMAL (gra w wysokim rejestrze, a wysokie dźwięki są lekko
rozstrojone). Ustaw **CLOCK** na **16-BIT**, by mieć dokładny, czysty strój.

**Moja melodia gra, ale przytrzymany dźwięk ciągle się ponawia / klika w pętli.**
Trzymaj dźwięk dłużej podczas nagrywania — przytrzymane dźwięki zapisują się jako
jedno uderzenie plus „przedłużenia” (ties), więc wybrzmiewają płynnie. Bardzo
krótkie przerwy między dźwiękami mogą brzmieć szarpiąco; to normalne.

**Nie mogę znaleźć regulatora.**
Wychylaj dalej w górę albo w dół — zaznaczenie przewija przez *wszystkie* regulatory
na wszystkich trzech stronach i zawija się. Patrz na znacznik `>`.

**Zmiana OCTAVE nie zmieniła dźwięku, który już gra.**
Oktawa wpływa tylko na *następny* zagrany dźwięk; dźwięki już wybrzmiewające
zachowują swoją wysokość.

**Sekwencer nie nagrywa perkusji.**
Najpierw upewnij się, że **DRUM > 0**, a potem naciskaj `1` podczas nagrywania.

---

## 8. Wskazówki

- **Graj podczas kręcenia.** Przytrzymaj dźwięk (albo użyj OPTION) i reguluj
  gałkę, by na żywo słyszeć, co robi.
- **Zacznij od presetu.** Wczytaj slot, który Ci się podoba (5.11), a potem
  modyfikuj od niego.
- **Na czyste solo:** zegar 16-BIT + odrobina LFO DEPTH; dodaj HP FILTER, by
  rozjaśnić, albo PORTA dla glissand.
- **Na pad:** wolny ATTACK i RELEASE, wysoki SUSTAIN, odrobina DETUNE,
  przytrzymane przez OPTION.
- **Zbuduj groove:** nagraj krótką melodię (5.9), dograj ścieżkę perkusji (5.10),
  ustaw TEMPO i niech pętla gra, a Ty graj do tego na wierzchu.
- **Zgubiłeś brzmienie, które miałeś?** Jeśli zapisałeś je do presetu (5.11), po
  prostu ponownie wybierz ten slot.

Baw się dobrze!
