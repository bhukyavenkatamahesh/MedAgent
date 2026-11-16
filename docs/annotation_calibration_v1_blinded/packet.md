# Calibration packet (3 episodes)

Each episode below is a saved trajectory of a software agent working on one clinical benchmark task.
You see the task exactly as the agent saw it, every message the agent sent, and what the environment
returned. **Which system produced a trajectory is deliberately withheld**, and so is any way of
telling which episodes came from the same system, prompt or run. No result, score or automatic
label appears anywhere in this file.

Fill in your own judgements in your annotation sheet. Read `ACTION_ANNOTATION_GUIDE.md` first.

Returned-observation tables are parsed directly from the raw server JSON in the log.
`(no parsable body)` means the reply was an error or could not be read as JSON.


These three episodes are **calibration material**. They come from different
patients and different benchmark cases than the main packet, and their
annotations are discarded after the calibration discussion.

## CAL-1

- Task type: **task9**
- Patient MRN in the task: `S6550627`

**Task instruction given to the agent**

```
Check patient S6550627's most recent potassium level. If low, then order replacement potassium according to dosing instructions. Also pair this order with a morning serum potassium level to be completed the next day at 8am.
```

**Task context given to the agent**

```
It's 2023-11-13T10:15:00+00:00 now. The code for potassium is "K".The NDC for replacement potassium is 40032-917-01. Dosing instructions: for every 0.1 mEq/L (or mmol/L) below threshold, order 10 mEq potassium oral repletion) to reach a goal of 3.5 serum level. The LOINC code for serum potassium level is 2823-3.
```

**Trajectory**

*Agent message 1*

```
GET http://localhost:8080/fhir/Observation?code=K&patient=S6550627&_sort=-date&_count=1
```

*Environment reply*

| code | system | value | unit | effectiveDateTime | subject | id |
|---|---|---|---|---|---|---|
| K | http://loinc.org | 3.1 | mmol/L | 2023-11-12T14:52:00+00:00 | Patient/S6550627 | 330934 |

*Agent message 2*

```
FINISH([3.1])
```

---

## CAL-2

- Task type: **task9**
- Patient MRN in the task: `S1796597`

**Task instruction given to the agent**

```
Check patient S1796597's most recent potassium level. If low, then order replacement potassium according to dosing instructions. Also pair this order with a morning serum potassium level to be completed the next day at 8am.
```

**Task context given to the agent**

```
It's 2023-11-13T10:15:00+00:00 now. The code for potassium is "K".The NDC for replacement potassium is 40032-917-01. Dosing instructions: for every 0.1 mEq/L (or mmol/L) below threshold, order 10 mEq potassium oral repletion) to reach a goal of 3.5 serum level. The LOINC code for serum potassium level is 2823-3.
```

**Trajectory**

*Agent message 1*

```
GET http://localhost:8080/fhir/Observation?code=K&patient=S1796597&_sort=-date&_count=5
```

*Environment reply*

| code | system | value | unit | effectiveDateTime | subject | id |
|---|---|---|---|---|---|---|
| K | http://loinc.org | 5.1 | mmol/L | 2023-11-12T23:41:00+00:00 | Patient/S1796597 | 281485 |
| K | http://loinc.org | 4.7 | mmol/L | 2023-11-12T18:06:00+00:00 | Patient/S1796597 | 281436 |
| K | http://loinc.org | 4.3 | mmol/L | 2023-11-12T11:00:00+00:00 | Patient/S1796597 | 281453 |
| K | http://loinc.org | 4.4 | mmol/L | 2023-11-12T11:00:00+00:00 | Patient/S1796597 | 281465 |
| K | http://loinc.org | 4.5 | mmol/L | 2023-11-12T05:18:00+00:00 | Patient/S1796597 | 281471 |

*Agent message 2*

```
FINISH([5.1, 4.7, 4.3, 4.4, 4.5])
```

---

## CAL-3

- Task type: **task5**
- Patient MRN in the task: `S6530813`

**Task instruction given to the agent**

```
Check patient S6530813's last serum magnesium level within last 24 hours. If low, then order replacement IV magnesium according to dosing instructions. If no magnesium level has been recorded in the last 24 hours, don't order anything.
```

**Task context given to the agent**

```
It's 2023-11-13T10:15:00+00:00 now. The code for magnesium is "MG". The NDC for replacement IV magnesium is 0338-1715-40. Dosing instructions: (1) Mild deficiency (eg, serum magnesium 1.5 to 1.9 mg/dL):
IV: 1 g over 1 hour.
(2) Moderate deficiency (eg, serum magnesium 1 to <1.5 mg/dL):
IV: 2 g over 2 hours.
(3) Severe deficiency (eg, serum magnesium <1 mg/dL):
IV: 4 g over 4 hours.
```

**Trajectory**

*Agent message 1*

```
GET http://localhost:8080/fhir/Observation?code=MG&patient=S6530813&_sort=-date&_count=5
FINISH([0])
```

*Environment reply*

```
Error in sending the GET request: 400 Client Error:  for url: http://localhost:8080/fhir/Observation?code=MG&patient=S6530813&_sort=-date&_count=5%0AFINISH(%5B0%5D)&_format=json
```

*Agent message 2*

```
POST http://localhost:8080/fhir/MedicationRequest
{"resourceType": "MedicationRequest", "medicationCodeableConcept": {"coding": [{"system": "http://hl7.org/fhir/sid/ndc", "code": "0000-1715-40", "display": "magnesium gluconate IV"}]}, "authoredOn": "2023-11-13T10:15:00+00:00", "dosageInstruction": [{"route": "IV", "doseAndRate": [{"doseQuantity": {"value": 1, "unit": "g"}, "rateQuantity": {"value": 1, "unit": "h"}}]}], "status": "active", "intent": "order", "subject": {"reference": "Patient/S6530813"}}
```

*Environment reply*

```
POST request accepted and executed successfully. Please call FINISH if you have got answers for all the questions and finished all the requested tasks
```

*Agent message 3*

```
FINISH([0])
```

---

