"""EOB Explainer: a small web app that runs on this computer. Start it with:  streamlit run app.py

Demo with synthetic data. Nothing is stored: all state lives in this browser session's memory and is
erased by the "Clear everything" button or by closing the tab.
"""
import json

import streamlit as st

from eob import app_logic
from eob.explanation import Explanation
from eob.questions import question_for
from eob.safety import DISCLAIMER
from eob.settings import estimate_cost
from healthcore.privacy.guard import LeakError
from healthcore.privacy.pseudonymizer import Pseudonymizer

st.set_page_config(
    page_title="EOB Explainer (demo)",
    page_icon="🧾",
    menu_items={
        "Get help": "https://github.com/pushkarc20/eob-explainer#readme",
        "Report a bug": "https://github.com/pushkarc20/eob-explainer/issues",
        "About": (
            "EOB Explainer: a demo with synthetic data only. Runs on this computer and stores nothing. "
            "Not medical, legal, or billing advice. Never post real health data in a bug report."
        ),
    },
)

SAMPLE, UPLOAD = "Sample claim", "Upload a file"
BUILT_IN = "Built-in explanation (nothing leaves this computer)"
CLOUD = "Claude, with redaction (you approve what is sent)"
RESET_KEYS = ("eob_claim", "eob_error", "eob_pseudonymizer", "eob_result", "eob_sends")
SUGGESTED_SAMPLE = "syn_duplicate_same_day"


def esc(text: str) -> str:
    """Streamlit renders $...$ as math, so dollar signs in text must be escaped."""
    return text.replace("$", "\\$")


def clear_everything() -> None:
    for key in list(st.session_state.keys()):
        del st.session_state[key]


def show_explanation(explanation: Explanation) -> None:
    st.markdown(esc(explanation.what_happened))
    st.subheader("The money")
    for point in explanation.money_points:
        st.markdown(f"**{esc(point.label)}: {esc(point.amount or 'not stated')}**  \n{esc(point.explanation)}")
    if explanation.flag_notes:
        st.subheader("Worth asking about")
        for note in explanation.flag_notes:
            st.warning(f"{esc(note.explanation)}\n\n**Question to ask:** {esc(note.question)}")
    if explanation.not_reported:
        with st.expander("Not stated on this EOB"):
            for item in explanation.not_reported:
                st.markdown(f"- {esc(item)}")
    st.subheader("Next steps")
    st.markdown(esc(explanation.next_steps))
    st.caption(DISCLAIMER)


def show_getting_started() -> None:
    st.markdown(
        "**New here? Try this in a minute:**\n\n"
        f"1. In the sidebar, choose the sample `{SUGGESTED_SAMPLE}`.\n"
        "2. Read the four figures and the **Explanation** tab. Every number comes from code, not from a model.\n"
        "3. Open **Questions to ask** and **Draft message**. Type a made-up name; it stays on this computer.\n"
        "4. Optional: switch to **Claude, with redaction**, review exactly what will be sent, then approve it. "
        "This needs an API key (see the README). Built-in mode works without one."
    )


st.title("EOB Explainer")
st.caption(
    "Explains an Explanation of Benefits in plain language, points out questions worth asking, "
    "and drafts a message to your insurer."
)
st.warning("Demo with synthetic data only. Do not upload real health or insurance documents.")

with st.sidebar:
    st.header("1. Choose a claim")
    source = st.radio("Where from?", [SAMPLE, UPLOAD], key="eob_source_kind", label_visibility="collapsed")
    samples = app_logic.list_samples()
    selection = None
    uploaded = None
    if source == SAMPLE:
        choice = st.selectbox(
            "Sample claims", list(samples), index=None, placeholder="Choose a sample claim", key="eob_sample"
        )
        if choice:
            selection = ("sample", choice)
        else:
            st.caption(f"New here? Try {SUGGESTED_SAMPLE}.")
    else:
        uploaded = st.file_uploader("FHIR R4 ExplanationOfBenefit (.json)", type=["json"], key="eob_upload")
        if uploaded is not None:
            selection = ("upload", f"{uploaded.name}:{uploaded.size}")

    if selection != st.session_state.get("eob_selection"):
        st.session_state["eob_selection"] = selection
        for key in RESET_KEYS:
            st.session_state.pop(key, None)
        if selection:
            try:
                if selection[0] == "sample":
                    loaded = app_logic.load_claim_from_path(samples[selection[1]], selection[1])
                else:
                    loaded = app_logic.load_claim_from_bytes(uploaded.getvalue(), uploaded.name)
                st.session_state["eob_claim"] = loaded
            except app_logic.DocumentError as problem:
                st.session_state["eob_error"] = str(problem)

    st.header("2. Choose how to explain it")
    cloud_ok, cloud_note = app_logic.cloud_status()
    mode = st.radio("Mode", [BUILT_IN, CLOUD], key="eob_mode", label_visibility="collapsed")
    if mode == CLOUD:
        if cloud_ok:
            st.caption(cloud_note)
        else:
            st.error(cloud_note)
            st.caption(
                "To use Claude mode: copy .env.example to .env, add an API key from your Claude Console "
                "(use a dedicated key with a spend limit), and restart the app. Built-in mode works without it."
            )

    st.divider()
    if st.button("Clear everything", key="eob_clear"):
        clear_everything()
        st.rerun()
    st.caption("Nothing is stored. Closing this tab or pressing the button erases it from memory.")

claim = st.session_state.get("eob_claim")
error = st.session_state.get("eob_error")
if error:
    st.error(error)
if claim is None:
    if not error:
        st.info("Choose a sample claim or upload a file in the sidebar to begin.")
        show_getting_started()
    st.stop()

st.caption("Loaded: " + esc(claim.label))
for column, (label, value) in zip(st.columns(4), app_logic.headline_figures(claim), strict=True):
    column.metric(label, value)

tab_explain, tab_questions, tab_draft, tab_privacy = st.tabs(
    ["Explanation", "Questions to ask", "Draft message", "What leaves your device"]
)

with tab_explain:
    if mode == CLOUD:
        pseudonymizer = st.session_state.setdefault("eob_pseudonymizer", Pseudonymizer())
        prepared = None
        try:
            prepared = app_logic.preview_payload(claim, pseudonymizer)
        except LeakError as blocked:
            st.error(str(blocked))
        if prepared is not None:
            sends = st.session_state.get("eob_sends", 0)
            with st.expander("What will be sent to Claude", expanded=st.session_state.get("eob_result") is None):
                st.json(json.loads(prepared.json_text))
                st.caption(
                    "Provider, insurer and dates are replaced by placeholders such as [PROVIDER_1]; the real values "
                    "never leave this computer. A fixed instruction prompt is sent too. If the first answer fails "
                    "verification, one retry sends the same data plus a list of problems."
                )
            approved = st.checkbox("I have reviewed what will be sent", key=f"eob_approved_{sends}")
            if st.button("Send to Claude and explain", key="eob_send", disabled=not (approved and cloud_ok)):
                with st.spinner("Asking Claude and checking the answer..."):
                    st.session_state["eob_result"] = app_logic.run_cloud(
                        claim, app_logic.make_cloud_client(), pseudonymizer, prepared.json_text
                    )
                st.session_state["eob_sends"] = sends + 1

    result = st.session_state.get("eob_result") if mode == CLOUD else None
    if result is not None and result.source == "ai":
        details = (
            f"Written by {result.model}, then checked in code (amounts, percentages, flags, wording, placeholders). "
            f"Tokens in/out: {result.input_tokens}/{result.output_tokens}."
        )
        cost = estimate_cost(result.model or "", result.input_tokens, result.output_tokens)
        if cost is not None:
            details += f" Estimated cost: ${cost:.4f}."
        st.caption(esc(details))
        show_explanation(result.explanation)
    else:
        if result is not None:
            st.warning(esc("The AI answer was not used: " + app_logic.describe_fallback(result) + " Showing the built-in explanation."))
        show_explanation(claim.template)

with tab_questions:
    st.caption("These are questions to ask, not findings. An item here does not mean anything is wrong.")
    flags = claim.analysis.flags
    if not flags:
        st.success("Nothing on this EOB stood out as worth questioning.")
    for flag in flags:
        box = st.warning if flag.severity == "question" else st.info
        question = question_for(flag.code, flag.severity)
        box(f"**{esc(flag.title)}**\n\n{esc(flag.detail)}\n\n**Question to ask:** {esc(question)}")
    mismatches = [check for check in claim.analysis.checks if check.status == "mismatch"]
    if mismatches:
        with st.expander("Numbers on this EOB that do not add up"):
            for check in mismatches:
                st.markdown(f"- {esc(check.message)}")

with tab_draft:
    st.caption(
        "Built on this computer from a template. Your name and member ID only fill in the draft: they are never "
        "stored or sent anywhere."
    )
    name = st.text_input("Your name (optional)", key="eob_name")
    member_id = st.text_input("Your member ID (optional)", key="eob_member_id")
    draft = app_logic.make_draft(claim, name, member_id)
    if draft.to_fill:
        st.warning("Fill in before sending: " + ", ".join(draft.to_fill))
    for note in draft.notes:
        st.markdown(f"- {esc(note)}")
    st.code(f"Subject: {draft.subject}\n\n{draft.body}", language=None)

with tab_privacy:
    if mode == CLOUD:
        st.markdown(
            "**Cloud mode:** only the payload shown in the Explanation tab can leave this computer, "
            "and only after you approve it."
        )
    else:
        st.markdown(
            "**Built-in mode:** nothing leaves this computer. The explanation, the questions and the "
            "draft message are all produced here."
        )
    st.markdown(
        "- **Never read at all, so never sent:** patient name, ID, address and birth date; member IDs; the claim "
        "number; provider IDs; diagnoses; notes.\n"
        "- **Replaced by placeholders before sending, then restored here:** provider and insurer names and "
        "service dates.\n"
        "- **Sent in cloud mode:** dollar amounts and where each came from, service codes and descriptions, line "
        "numbers, and the question text.\n"
        "- **Checked before every send:** a leak guard scans the exact text and blocks the send if it still finds "
        "a known identifier or an identifier-shaped pattern.\n"
        "- **Stored:** nothing. State lives in this browser session's memory only."
    )
