import os
import pandas as pd
import streamlit as st
from PIL import Image
from reportlab.platypus import Table, TableStyle
from ai_part import ai_generate_description, generate_pdf_report
from opencv_logic import apply_logo_realistic
from reportlab.lib import colors
from reportlab.lib.units import cm
from streamlit_drawable_canvas import st_canvas

# ----------------- CONFIG -----------------
UPLOAD_DIR = "uploads"
OUTPUT_DIR = "outputs"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ----------------- HELPERS -----------------
@st.cache_data(show_spinner=False)
def load_image(path):
    return Image.open(path).convert("RGBA")


def save_uploaded_file(uploaded_file, folder=UPLOAD_DIR):
    """Save Streamlit uploaded file to disk and return path."""
    os.makedirs(folder, exist_ok=True)
    file_path = os.path.join(folder, uploaded_file.name)
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return file_path


# ----------------- STREAMLIT APP -----------------
st.set_page_config(page_title="Logo Placement Tool", layout="wide")
st.title("🧢 Tech Pack Logo Placement Tool")

# Initialize session state
if "results" not in st.session_state:
    st.session_state.results = []
if "logo_path" not in st.session_state:
    st.session_state.logo_path = None
if "w_cm" not in st.session_state:
    st.session_state.w_cm = 5.0
if "h_cm" not in st.session_state:
    st.session_state.h_cm = 5.0

# --- Step 0: Upload Excel ---
st.subheader("Step 0: Upload Excel & Select Data Range")
excel_file = st.file_uploader("Upload Excel File", type=["xlsx", "xls"], key="excel_upload")

excel_path = None
design_data = []
key_col_input = ""
value_col_input = ""
start_row = 0
end_row = None

if excel_file:
    excel_path = save_uploaded_file(excel_file)
    df = pd.read_excel(excel_file, header=None)
    total_rows = len(df)
    st.write(f"📊 Total rows detected: {total_rows}")

    key_col_input = st.text_input("Enter column name for Keys (renamed)").strip()
    value_col_input = st.text_input("Enter column name for Values (renamed)").strip()
    start_row = st.number_input("Start Row (1-indexed)", min_value=1, max_value=total_rows, value=1, step=1)
    end_row = st.number_input("End Row (1-indexed)", min_value=1, value=total_rows, step=1)

    if st.button("📥 Fetch Data from Excel"):
        subset = df.iloc[start_row - 1 : end_row, [1, 2]].dropna()
        subset.columns = [key_col_input or "Key", value_col_input or "Value"]
        design_data = subset.values.tolist()
        st.success(f"✅ Fetched {len(subset)} rows.")
        st.dataframe(subset)


# --- Step 1: Upload Logo ---
st.subheader("Step 1: Upload Logo Image")
logo_file = st.file_uploader("Upload Logo Image", type=["png", "jpg", "jpeg"], key="logo_upload")

if logo_file:
    logo_path = save_uploaded_file(logo_file)
    st.session_state.logo_path = logo_path
    st.success("✅ Logo uploaded.")


# --- Step 2: Logo size ---
st.subheader("Step 2: Define Approximate Logo Size (for PDF Report)")
st.info("This size is for the text description in the final report. The visual size is determined by the area you draw.")
col_w, col_h = st.columns(2)
with col_w:
    st.session_state.w_cm = st.number_input("Width (cm)", min_value=1.0, value=st.session_state.w_cm, step=0.5)
with col_h:
    st.session_state.h_cm = st.number_input("Height (cm)", min_value=1.0, value=st.session_state.h_cm, step=0.5)


# --- Step 3: Upload and Place Logo on Cap ---
st.subheader("Step 3: Upload and Place Logo on Cap")
st.info(
    "**HOW TO USE:** 1. Click 4 corners in clockwise order (Top-Left → Top-Right → Bottom-Right → Bottom-Left). "
    "**2. Double-click the 4th point to finalize the shape.** A preview will then appear."
)

cap_file = st.file_uploader(
    "Upload Cap/Base Image", type=["png", "jpg", "jpeg"], key=f"cap_{len(st.session_state.results)}"
)

if cap_file:
    cap_path = save_uploaded_file(cap_file)
    cap_image = load_image(cap_path)

    max_width = 600
    scale = max_width / cap_image.width
    display_size = (max_width, int(cap_image.height * scale))
    cap_resized = cap_image.resize(display_size)

    canvas_result = st_canvas(
        fill_color="rgba(255, 165, 0, 0.3)",
        stroke_width=2,
        stroke_color="red",
        background_image=cap_resized,
        update_streamlit=True,
        height=display_size[1],
        width=display_size[0],
        drawing_mode="polygon",
        key=f"canvas_{len(st.session_state.results)}",
    )

    if canvas_result.json_data and canvas_result.json_data["objects"]:
        last_object = canvas_result.json_data["objects"][-1]
        if last_object["type"] == "path" and len(last_object["path"]) == 5:
            points = last_object["path"]
            dest_points = [(p[1] / scale, p[2] / scale) for p in points[:4]]

            if st.session_state.logo_path:
                os.makedirs(OUTPUT_DIR, exist_ok=True)
                out_path = os.path.join(OUTPUT_DIR, os.path.splitext(cap_file.name)[0] + "_with_logo.png")
                applied = apply_logo_realistic(cap_path, st.session_state.logo_path, dest_points, out_path)
                if applied:
                    st.image(applied, caption="Preview", width=400)

                    placement = st.text_input(
                        "Placement description (e.g., Front Panel)",
                        "Front Panel",
                        key=f"placement_{len(st.session_state.results)}",
                    )

                    if st.button("✅ Save This Cap", key=f"save_{len(st.session_state.results)}"):
                        ai_desc = ai_generate_description(
                            placement, (st.session_state.w_cm, st.session_state.h_cm), cap_file.name
                        )
                        st.session_state.results.append(
                            {
                                "image": cap_path,
                                "logo": st.session_state.logo_path,
                                "size_cm": (st.session_state.w_cm, st.session_state.h_cm),
                                "placement": placement,
                                "description": ai_desc,
                                "output": out_path,
                            }
                        )
                        st.success("Cap saved! Upload another image or generate the report below.")
                        st.experimental_rerun()


# --- Step 4: Generate PDF ---
if st.session_state.results:
    st.markdown("---")
    st.header("Final Report")
    st.write(f"📦 You have added **{len(st.session_state.results)}** cap views so far.")

    cols = st.columns(min(len(st.session_state.results), 4))
    for i, result in enumerate(st.session_state.results):
        with cols[i % 4]:
            st.image(result["output"], caption=result["placement"], use_column_width=200)

    if st.button("📄 Generate PDF Report"):
        generate_pdf_report(
            st.session_state.results,
            pdf_path=os.path.join(OUTPUT_DIR, "logo_techpack.pdf"),
            excel_file=excel_path,
            excel_columns={"indices": [1, 2], "names": [key_col_input or "Key", value_col_input or "Value"]},
            excel_start_row=start_row - 1,
            excel_end_row=end_row,
        )

        with open(os.path.join(OUTPUT_DIR, "logo_techpack.pdf"), "rb") as f:
            st.download_button("⬇️ Download Techpack PDF", f, file_name="logo_techpack.pdf")
