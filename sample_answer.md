# Comments semi long examples with answers

## Orto

Henv 28.11.24. Kreftpas. Rullator. Takket nei til time 10.12.24. Pas avbest samme dag 11.03 - sier han ikke kom frem på telefon i går/tar kontakt når han ønsker time/ABC 10.03.25

ground truth: (no info)

Kpol 260525 EKG/lab asa III. avbestile 23.09. **Ønsker fra okt pga** sykepenger jf gul lapp kpol 070725 + (planleggers int)

ground truth: (availability  **Ønsker fra okt pga**)

AVVENT. Sendt gul lapp til ABC om videre forløp. DEF 14.09.25 kpol 23.03.25. Ønsker op i okt/nov 25, rtg, lab, asa 2 BMI 30

ground truth: (no info - on hold doesnt mean patient_ready = false)

Opl mld 27.03.25, men er gravid skal derfor ikke opr før jan -26. ABC 08.10.25. Må konf med DEF. 100. DEF + GHI 

ground truth: (patient_ready=true, availability not : jan -26. or available from)

KPOL 3.4.25. Opr med ABC som ass jfr DEF, lab ikke tatt - behøver ikke jfr DEF 10.04.25 ilm. kort varsel, asa 2, BMI 31

ground truth: (short notice = true)

## ØNH

Gifter seg i sept -23. ringes til 2 mnd preopr. Lunge anestesitilsyn ? ABC

ground truth: (maybe unavailable but if the date has passed then dont care)

Kjeveopr først, usikker på når hun får denne, skal holde oss oppdatert jmf 13.08.25, Pas ønsker å bli oppringt for tilpassing av opr. Stue 11

ground truth: (patient_ready=false)

Stue 11. Kort varsel. Ferie 23.06. Ønsker sent sent september el tildlig oktober 25.

ground truth: (unavailable on that day - possible if you just click that day short notice = true Kort varsel.)

Pas tar kontakt når han er klar for opr. Behandles nå for Laukemi 31.10 24 ABC, svar 31/10 -24 Ferie 05-25.06 + 10.09-15.10.24. Stue 11. Klar til opr jmf Anestesi

ground truth: (thats why right now gt has 2 unavailable periods but shold not be like this, patient_ready=true -makes the most sense.)

Pas. gir beskjed når han har sluttet med Isotretonin 30/4-25 evt litt før ABC HLOS pas. Ikke DEF. Kan opr av LIS. Stue 11.

ground truth: (**Patient Ready=false)**
