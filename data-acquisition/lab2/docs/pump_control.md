# Pumbajuhtimise võrdluse tööleht

See fail täidetakse sama katseprotokolli järgi kogutud `raw` ja `opamp` andmetega. Allpool olev Labori 1 ajalooline lähtejoon pärineb kontrollitud repoallikatest; Labor 2 võrdlustabelitesse lähevad uued sama protokolli mõõtmised.

See on Labor 2 võrdlusmall ega asenda ega muuda Labor 1 ajaloolist `docs/pump_control.md` faili. Ametlik ülesanne nõuab uute tulemuste lisamist vanade väärtuste alla, kuid kursuse repositoorium eraldab laborite failid kataloogidesse `lab1/` ja `lab2/`.

TODO: enne rakendamist otsustada õppejõuga, kas Labor 2 lõplikud tulemused jäävad siia koos viitega Labor 1 ajaloole või tuleb need lisada ka ajaloolisse Labor 1 faili. Kuni otsus puudub, Labor 1 faili ei muudeta.

## Labor 1 ajalooline raw-lähtejoon

Allikas: `data-acquisition/lab1/docs/pump_control.md`. Need arvud kirjeldavad Labori 1 otseühendatud MPX5700AP süsteemi ega ole Labor 2 op-amp tulemused.

| Näitaja | Labor 1 kinnitatud väärtus | Piirang / allikas |
|---|---:|---|
| Väljalülitusrõhk | `−60 kPa` | Lõplik seadistus; varasem `−75 kPa` oli sellel stendil saavutamatu |
| Sisselülitusrõhk | `−40 kPa` | Lõplik seadistus |
| Minimaalne väljalülitusaeg | `15 s` | Kehtib automaatsetele taaskäivitustele |
| Käivituste ülempiir | `4/min` | Kehtib automaatsetele taaskäivitustele; see ei ole iga katse tegelik käivitussagedus |
| Klaas õhus, hoidmine | `0` automaatset taaskäivitust `120 s` jooksul | `lab1_ownbox_hold_air_02.10.26.csv`, rõhk `−77 → −44 kPa` |
| Klaas õhus, teine hoidmine | `0` automaatset taaskäivitust `60 s` jooksul | `lab1_ownbox_hold_air_fw2_02.10.26.csv`, rõhk `−81 → −57 kPa`, `100,0 Hz` |
| Pumba töötsükkel kümne võtmise ajal | `45,2%` | Tavavõtmine; `lab1_pick10_fw3_02.10.26.csv` |
| Pumba töötsükkel kümne lähenemisega võtmise ajal | `29,2%` | `lab1_approach_pick10_02.10.26.csv` |

Labori 1 eraldi anduritestis oli raw-müra atmosfääril `4,84 LSB` ja passiivselt hoitud vaakumil `3,68 LSB`. Teises aknas pump enam ei töötanud, seega ei kirjelda see aktiivse mootori müra. Allikas: `data-acquisition/lab1/docs/sensor_choice.md`. Neid väärtusi ei kasutata Labor 2 SNR-ina.

## Mõõtekonfiguratsioonid

| Väli | Raw | Opamp |
|---|---|---|
| CSV fail | Labori 1 ajalooliste failide skeem `t_ms,adc,p_kpa,pump`; Labor 2: `data/pulses_2026-11-15.csv` (`config=raw`) | `data/pulses_2026-11-15.csv` (`config=opamp`) |
| `config` väärtus | `raw` | `opamp` |
| Diskreetimissagedus (Hz) | Labor 1: `1002` rida / `10010 ms` ≈ `100,1 Hz`; Labor 2: 100,0 Hz (1001 rida / 10 s, `missed=0`) | 100,0 Hz |
| Anduri ja ADC konfiguratsioon | Labor 1: MPX5700AP otse AtomS3R G5-le, 12 bit, `ADC_11db`, kaheksa lugemi keskmine | MPX5700AP + LM358N (A 1,185, `Vref` ~0,69 V) + 3,3 kΩ / 0,1 µF → G5, 12 bit, `ADC_11db`, kaheksa lugemi keskmine |
| Katseprotokoll | 15.11 `pulse_series.py`: 3 s väljas, 4 s puhumine, 3 s väljas, 30 jooksu | sama |

## Olukordade võrdlus

| Olukord | Konfiguratsioon | Kontrollriba (kPa) | Minimaalne väljalülitusaeg (s) | Käivitused minutis | Märkused |
|---|---|---:|---:|---:|---|
| Napp klaasil | raw | Labor 1 ajalooline `on −40 / off −60`; Labor 2: ei mõõdetud (Raimo otsus 15.11: juhtimisloogika ja riba ei muutunud) | Labor 1 ajalooline `15`; Labor 2: ei mõõdetud (Raimo otsus 15.11: juhtimisloogika ja riba ei muutunud) | Labor 1 hoidmiskatses `0/min` `120 s` jooksul; Labor 2: ei mõõdetud (Raimo otsus 15.11: juhtimisloogika ja riba ei muutunud) | Klaas oli õhus |
| Napp klaasil | opamp | ei mõõdetud (Raimo otsus 15.11: juhtimisloogika ja riba ei muutunud) | ei mõõdetud (Raimo otsus 15.11: juhtimisloogika ja riba ei muutunud) | ei mõõdetud (Raimo otsus 15.11: juhtimisloogika ja riba ei muutunud) | |
| Napp õhus | raw | Labor 1 ajalooline `on −40 / off −60`; Labor 2: ei mõõdetud (Raimo otsus 15.11: juhtimisloogika ja riba ei muutunud) | Labor 1 ajalooline `15`; Labor 2: ei mõõdetud (Raimo otsus 15.11: juhtimisloogika ja riba ei muutunud) | ei mõõdetud (Raimo otsus 15.11: juhtimisloogika ja riba ei muutunud) | Labor 1 varasem katse ei kasutanud lõplikku Labor 2 protokolli |
| Napp õhus | opamp | ei mõõdetud (Raimo otsus 15.11: juhtimisloogika ja riba ei muutunud) | ei mõõdetud (Raimo otsus 15.11: juhtimisloogika ja riba ei muutunud) | ei mõõdetud (Raimo otsus 15.11: juhtimisloogika ja riba ei muutunud) | |
| Voolik korgiga | raw | Labor 1 ajalooline `on −40 / off −60`; Labor 2: ei mõõdetud (Raimo otsus 15.11: juhtimisloogika ja riba ei muutunud) | Labor 1 ajalooline `15`; Labor 2: ei mõõdetud (Raimo otsus 15.11: juhtimisloogika ja riba ei muutunud) | ei mõõdetud (Raimo otsus 15.11: juhtimisloogika ja riba ei muutunud) | Labor 1 varasem katse ei kasutanud lõplikku Labor 2 protokolli |
| Voolik korgiga | opamp | ei mõõdetud (Raimo otsus 15.11: juhtimisloogika ja riba ei muutunud) | ei mõõdetud (Raimo otsus 15.11: juhtimisloogika ja riba ei muutunud) | ei mõõdetud (Raimo otsus 15.11: juhtimisloogika ja riba ei muutunud) | |
| Poolik haare | raw | ei mõõdetud (Raimo otsus 15.11: juhtimisloogika ja riba ei muutunud) | ei mõõdetud (Raimo otsus 15.11: juhtimisloogika ja riba ei muutunud) | ei mõõdetud (Raimo otsus 15.11: juhtimisloogika ja riba ei muutunud) | |
| Poolik haare | opamp | ei mõõdetud (Raimo otsus 15.11: juhtimisloogika ja riba ei muutunud) | ei mõõdetud (Raimo otsus 15.11: juhtimisloogika ja riba ei muutunud) | ei mõõdetud (Raimo otsus 15.11: juhtimisloogika ja riba ei muutunud) | |

## Lahutusvõime ja signaali kvaliteet

| Näitaja | Raw | Opamp | Arvutus / allikas |
|---|---:|---:|---|
| Pa ühe ADC sammu kohta | Labor 1 arvutus `0,1405 kPa/kood = 141 Pa/kood`; Labor 2: 141,9 Pa/kood | 119,8 Pa/kood | `q_P = q_V / S_P` koos vastava astme võimendusega |
| Signaalitase (kPa) | 242,8 | 242,6 | sama Labor 2 impulsi platoo keskmine − baasjoone keskmine |
| Platoo müra standardhälve (kPa) | 1,387 | 0,681 | sama ajavahemik ja ühikud; Labor 1 LSB-vaatlus ei asenda seda |
| SNR (dB) | 46,0 | 51,5 | `20 · log10(|signal| / noise_std)` |

- 15.11.26 märkus (andmelehe mudel, 30 + 30 impulssi, puhumine 4 s): Pa/kood `raw` 141,9 / `opamp` 119,8; impulsi suurus 242,8 / 242,6 kPa; platoo müra 1387 / 681 Pa; SNR 46,0 / 51,5 dB. [Arvutus](bench_session.md#kalibratsioon-pa-adc-samm-snr-ja-spektrid-1511-andmelehe-mudel). Pumbajuhtimise olukorrad (klaas, õhk, kork, poolik haare) on mõõtmata.

## Pooliku haarde eristamine

Laboris 1 poolikut haaret ei mõõdetud. Eristamise kriteerium ja läviväärtus: Laboris 2 ei mõõdetud (Raimo otsus 15.11).

| Konfiguratsioon | Eristamise aeg (s) | Algushetke määratlus | Meetod |
|---|---:|---|---|
| Raw | — | — | ei mõõdetud (Raimo otsus 15.11: juhtimisloogika ja riba ei muutunud) |
| Opamp | — | — | ei mõõdetud (Raimo otsus 15.11: juhtimisloogika ja riba ei muutunud) |

## Järeldus

- Kas kontrollriba muutus: ei, riba `on −40 / off −60 kPa` jäi samaks (aste ainult skaleerib signaali).
- Kas käivituste arv muutus: uue signaaliga ei mõõdetud (Raimo otsus 15.11).
- Kas lahutusvõime või SNR paranes: jah — 141,9 → 119,8 Pa/kood, müra pump väljas 539 → 176 Pa, SNR 46,0 → 51,5 dB ([arvutus](bench_session.md#kalibratsioon-pa-adc-samm-snr-ja-spektrid-1511-andmelehe-mudel)).
- Kas poolik haare eristus varem: ei mõõdetud; väiksem müra peaks eristamist pigem parandama (hinnang).
- Kas aste oli põhjendatud: jah — peenem samm, ~3× väiksem müra ja ~5,5 dB parem SNR; G5 jäi ≤ 3,0 V.
