"""MetaTox browser-based GUI."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import streamlit as st

from pipeline import (
    EnvironmentStatus,
    PipelineOptions,
    check_environment,
    get_work_dir,
    run_pipeline,
    sanitize_filename,
    summarize_outputs,
    zip_output_directory,
)


BIOTRANS_OPTIONS = {
    "allHuman": "All human biotransformations",
    "ecbased": "EC-based metabolism",
    "cyp450": "CYP450 metabolism",
    "phaseII": "Phase II conjugation",
    "hgut": "Human gut microbial",
    "superbio": "Superbio ordered steps",
    "envimicro": "Environmental microbial",
}

GLORYX_OPTIONS = {
    "phase_1_and_2": "Phase 1 and phase 2",
    "phase_1": "Phase 1 only",
    "phase_2": "Phase 2 only",
}


def init_state() -> None:
    defaults = {
        "logs": [],
        "is_running": False,
        "cancel_event": None,
        "last_output_dir": None,
        "last_zip": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def append_log(message: str) -> None:
    st.session_state.logs.append(message)


def render_environment(status: EnvironmentStatus) -> None:
    st.subheader("Environment")
    cols = st.columns(3)
    cols[0].metric("Singularity/Apptainer", "Ready" if status.singularity_available else "Missing")
    cols[1].metric("Metatox.sh", "Found" if status.metatox_script_found else "Missing")
    cols[2].metric("Work directory", str(status.work_dir))

    for note in status.notes:
        st.info(note)
    for issue in status.issues:
        st.error(issue)


def save_uploaded_file(upload) -> Path:
    input_dir = get_work_dir() / "data" / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    destination = input_dir / sanitize_filename(upload.name)
    destination.write_bytes(upload.getbuffer())
    return destination


def start_pipeline(options: PipelineOptions) -> None:
    st.session_state.is_running = True
    st.session_state.logs = []
    st.session_state.last_output_dir = None
    st.session_state.last_zip = None
    st.session_state.cancel_event = threading.Event()

    def worker() -> None:
        try:
            output_dir = run_pipeline(
                options,
                log_callback=append_log,
                cancel_event=st.session_state.cancel_event,
            )
            st.session_state.last_output_dir = output_dir
            zip_path = output_dir.parent / f"{output_dir.name}.zip"
            st.session_state.last_zip = zip_output_directory(output_dir, zip_path)
        except Exception as exc:  # noqa: BLE001
            append_log("")
            append_log(f"ERROR: {exc}")
        finally:
            st.session_state.is_running = False

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()


def main() -> None:
    st.set_page_config(
        page_title="MetaTox",
        page_icon="🧪",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    init_state()
    status = check_environment()

    st.title("MetaTox")
    st.caption(
        "In silico metabolite prediction with BioTransformer3, SygMa, GLORYx, MetaTrans, "
        "and optional Meta-Predictor."
    )

    with st.sidebar:
        st.header("Prediction options")
        biotrans_type = st.selectbox(
            "BioTransformer model",
            options=list(BIOTRANS_OPTIONS.keys()),
            format_func=lambda key: f"{key} — {BIOTRANS_OPTIONS[key]}",
        )
        nstep = st.number_input("BioTransformer steps", min_value=1, max_value=10, value=1)
        cmode = st.selectbox(
            "BioTransformer CYP450 mode",
            options=[1, 2, 3],
            index=2,
            help="1 = CypReact + rules, 2 = CyProduct only, 3 = combined",
        )
        phase1 = st.number_input("SygMa phase 1 cycles", min_value=1, max_value=10, value=1)
        phase2 = st.number_input("SygMa phase 2 cycles", min_value=1, max_value=10, value=1)
        phase_gloryx = st.selectbox(
            "GLORYx metabolism phase",
            options=list(GLORYX_OPTIONS.keys()),
            format_func=lambda key: GLORYX_OPTIONS[key],
        )
        outdir = st.text_input("Output folder name", value="Results_Prediction")
        predictor_activate = st.checkbox(
            "Enable Meta-Predictor",
            value=False,
            help="Requires CUDA and the Meta-Predictor repository inside the container.",
        )
        keep_tmp = st.checkbox("Keep intermediate files", value=False)

    tab_run, tab_results, tab_environment = st.tabs(["Run", "Results", "Environment"])

    with tab_run:
        st.subheader("Input")
        st.markdown(
            "Upload a text file with one molecule per line: `MoleculeName,SMILES`  \n"
            "Example: `Nicotine,CN1CCC[C@H]1c2cccnc2`"
        )

        uploaded = st.file_uploader("Input file", type=["txt", "csv"])
        example_file = get_work_dir() / "ExempleInput.txt"
        use_example = False
        if example_file.is_file():
            use_example = st.checkbox("Use bundled example input", value=False)

        col_run, col_cancel = st.columns([1, 1])
        run_clicked = col_run.button("Run prediction", type="primary", disabled=st.session_state.is_running)
        cancel_clicked = col_cancel.button("Cancel", disabled=not st.session_state.is_running)

        if cancel_clicked and st.session_state.cancel_event is not None:
            st.session_state.cancel_event.set()
            st.warning("Cancellation requested. Waiting for the current step to stop...")

        if run_clicked:
            if status.issues:
                st.error("Environment is not ready. Check the Environment tab.")
            else:
                try:
                    if uploaded is not None:
                        input_path = save_uploaded_file(uploaded)
                    elif use_example:
                        input_path = example_file
                    else:
                        raise ValueError("Upload an input file or enable the bundled example.")

                    options = PipelineOptions(
                        input_file=input_path,
                        outdir=outdir.strip() or "Results_Prediction",
                        biotrans_type=biotrans_type,
                        nstep=int(nstep),
                        cmode=int(cmode),
                        phase1=int(phase1),
                        phase2=int(phase2),
                        phase_gloryx=phase_gloryx,
                        predictor_activate=predictor_activate,
                        keep_tmp=keep_tmp,
                    )
                    start_pipeline(options)
                    st.success("Prediction started.")
                except Exception as exc:  # noqa: BLE001
                    st.error(str(exc))

        st.subheader("Log")
        log_text = "\n".join(st.session_state.logs) if st.session_state.logs else "No output yet."
        st.text_area("Pipeline output", value=log_text, height=360)

        if st.session_state.is_running:
            time.sleep(1.0)
            st.rerun()

    with tab_results:
        output_dir = st.session_state.last_output_dir
        if output_dir and Path(output_dir).exists():
            st.success(summarize_outputs(Path(output_dir)))
            zip_path = st.session_state.last_zip
            if zip_path and Path(zip_path).is_file():
                st.download_button(
                    label="Download results (.zip)",
                    data=Path(zip_path).read_bytes(),
                    file_name=Path(zip_path).name,
                    mime="application/zip",
                )
        else:
            st.info("Run a prediction to generate downloadable results.")

    with tab_environment:
        render_environment(status)
        st.markdown(
            """
            ### Container deployment

            This interface runs inside Docker and executes the original `Metatox.sh` pipeline
            with Singularity/Apptainer.

            **Quick start**

            ```bash
            docker compose up --build
            ```

            Then open [http://localhost:8501](http://localhost:8501).

            The first run may take longer while Singularity images are downloaded.
            """
        )
        if st.button("Refresh environment checks"):
            st.rerun()


if __name__ == "__main__":
    main()
