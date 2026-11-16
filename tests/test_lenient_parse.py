"""Lenient action extraction for small models that wrap actions in prose."""
from procsafe.adapters.medagentbench import extract_action, parse_history
from procsafe.schema import GET, INVALID, POST


def test_get_wrapped_in_prose():
    txt = "I will invoke the GET function.\n\nGET http://x/fhir/Observation?code=MG&patient=S1\n\nThe response will be JSON."
    assert extract_action(txt) == "GET http://x/fhir/Observation?code=MG&patient=S1"


def test_post_body_extracted():
    txt = 'Ordering now:\nPOST http://x/fhir/MedicationRequest\n{"resourceType": "MedicationRequest"}\nDone.'
    assert extract_action(txt) == 'POST http://x/fhir/MedicationRequest\n{"resourceType": "MedicationRequest"}'


def test_finish_extracted():
    assert extract_action("Answer:\nFINISH([3.9])\nThanks") == "FINISH([3.9])"


def test_no_action_stays_unchanged():
    assert extract_action("I am not sure what to do.") == "I am not sure what to do."


def test_strict_mode_unchanged_and_lenient_recovers():
    hist = [{"role": "user", "content": "task"},
            {"role": "agent", "content": "Let me check.\nGET http://x/fhir/Observation?code=K&patient=S1"}]
    assert parse_history(hist, "e")[0].action_type == INVALID
    t = parse_history(hist, "e", lenient=True)[0]
    assert t.action_type == GET and t.request == "http://x/fhir/Observation?code=K&patient=S1"


def test_tool_name_ignores_text_after_url():
    from procsafe.adapters.medagentbench import tool_name
    assert tool_name(POST, '{api_base}/Observation.Create {observationCode="potassium"} x=y') == "observation.create.create"
    assert tool_name(POST, "http://x/fhir/Observation junk junk") == "vital.create"
