import os
import pandas as pd
import streamlit as st
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import Table, TableStyle
from streamlit_drawable_canvas import st_canvas

from ai_part import ai_generate_description, generate_pdf_report
from opencv_logic import apply_logo_realistic

# --- CACHE LOADED IMAGES ---
@st.cache_data(show_spinner=False)
def load_image(path):
    return Image.open(path).convert("RGBA")

# --- FETCH EXCEL DATA ---
def fetch_key_value_table(file_path, start_row, end_row, column1, column2):
    df = pd.read_excel(file_path, header=None)
    subset = df.iloc[start_row - 1:end_row, [1, 2]].dropna()
    subset.columns = [column1, column2]
    return subset.values.tolist()

# --- STREAMLIT PAGE CONFIG ---
st.set_page_config(page_title="Logo Placement Tool", layout="wide")
st.title("🧢 Tech Pack Logo Placement Tool")

# --- INITIALIZE SESSION STATE ---
if "results" not in st.session_state:
    st.session_state.results = []

if "logo_path" not in st.session_state:
    st.session_state.logo_path = None

if "w_cm" not in st.session_state:
    st.session_state.w_cm = 5.0

if "h_cm" not in st.session_state:
    st.session_state.h_cm = 5.0

if "cap_images" not in st.session_state:
    st.session_state.cap_images = {}

if "canvas_objects" not in st.session_state:
    st.session_state.canvas_objects = {}

if "placement" not in st.session_state:
    st.session_state.placement = "Front Panel"

# --- STEP 0: UPLOAD EXCEL ---
st.subheader("Step 0: Upload Excel & Select Data Range")
excel_file = st.file_uploader("Upload Excel File", type=["xlsx", "xls"], key="excel_upload")
if excel_file:
    df = pd.read_excel(excel_file, header=None)
    total_rows = len(df)
    st.write(f"📊 Total rows detected: {total_rows}")

    key_col_input = st.text_input("Enter column name for Keys (renamed)").strip()
    value_col_input = st.text_input("Enter column name for Values (renamed)").strip()

    start_row = st.number_input("Start Row (1-indexed)", min_value=1, max_value=total_rows, value=1, step=1)
    end_row = st.number_input("End Row (1-indexed)", min_value=1, max_value=total_rows, value=total_rows, step=1)

    if st.button("📥 Fetch Data from Excel"):
        subset = df.iloc[start_row - 1:end_row, [1, 2]].dropna()
        if key_col_input and value_col_input:
            subset.columns = [key_col_input, value_col_input]
        else:
            subset.columns = ["Key", "Value"]
        st.success(f"✅ Fetched {len(subset)} rows.")
        st.dataframe(subset)

        design_data = subset.values.tolist()
        design_table = Table(design_data, colWidths=[7 * cm, 8 * cm])
        design_table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        st.info("Table ready for PDF export ✅")

# --- STEP 1: UPLOAD LOGO ---
st.subheader("Step 1: Upload Logo Image")
logo_file = st.file_uploader("Upload Logo Image", type=["png", "jpg", "jpeg"], key="logo_upload")
if logo_file:
    logo_filename = f"logo_{logo_file.name}"
    os.makedirs("uploads", exist_ok=True)
    logo_path = os.path.join("uploads", logo_filename)
    if st.session_state.logo_path is None or os.path.basename(st.session_state.logo_path) != logo_filename:
        logo = Image.open(logo_file).convert("RGBA")
        if logo_path.lower().endswith((".jpg", ".jpeg")):
            logo = logo.convert("RGB")
        logo.save(logo_path)
        st.session_state.logo_path = logo_path
        st.success("✅ Logo uploaded.")

# --- STEP 2: DEFINE LOGO SIZE ---
st.subheader("Step 2: Define Approximate Logo Size (for PDF Report)")
st.info("This size is for the text description in the final report. The visual size is determined by the area you draw.")
col_w, col_h = st.columns(2)
with col_w:
    st.session_state.w_cm = st.number_input("Width (cm)", min_value=1.0, value=st.session_state.w_cm, step=0.5)
with col_h:
    st.session_state.h_cm = st.number_input("Height (cm)", min_value=1.0, value=st.session_state.h_cm, step=0.5)

# --- STEP 3: UPLOAD CAP IMAGE AND DISPLAY CANVAS ---
st.subheader("Step 3: Upload and Place Logo on Cap")
st.info(
    "**HOW TO USE:** 1. Click 4 corners in clockwise order (Top-Left → Top-Right → Bottom-Right → Bottom-Left). "
    "**2. Double-click the 4th point to finalize the shape. A preview will appear.**"
)

cap_file = st.file_uploader("Upload Cap/Base Image", type=["png", "jpg", "jpeg"], key="cap_upload")
if cap_file:
    cap_filename = f"cap_{cap_file.name}"
    cap_path = os.path.join("uploads", cap_filename)
    os.makedirs("uploads", exist_ok=True)

    if cap_filename not in st.session_state.cap_images:
        cap_image = Image.open(cap_file).convert("RGBA")
        if cap_path.lower().endswith((".jpg", ".jpeg")):
            cap_image = cap_image.convert("RGB")
        cap_image.save(cap_path)

        max_width = 600
        scale = max_width / cap_image.width
        display_size = (max_width, int(cap_image.height * scale))
        cap_resized = cap_image.resize(display_size)

        st.session_state.cap_images[cap_filename] = {
            "original_path": cap_path,
            "resized_image": cap_resized,
            "scale": scale,
            "display_size": display_size
        }
    else:
        cached = st.session_state.cap_images[cap_filename]
        cap_path = cached["original_path"]
        cap_resized = cached["resized_image"]
        scale = cached["scale"]
        display_size = cached["display_size"]

    # --- CANVAS ---
    canvas_result = st_canvas(
        fill_color="rgba(255, 165, 0, 0.3)",
        stroke_width=2,
        stroke_color="red",
        background_image=cap_resized,
        height=display_size[1],
        width=display_size[0],
        drawing_mode="polygon",
        key="cap_canvas",
        update_streamlit=False,  # prevents constant rerun
    )

# --- Placement description ---
placement = st.text_input("Placement description (e.g., Front Panel)", value=st.session_state.placement, key="placement")

# --- PROCESS AND SAVE LOGO ---
if st.button("✅ Process Logo") and cap_file and st.session_state.logo_path:
    if canvas_result.json_data and canvas_result.json_data.get("objects"):
        last_object = canvas_result.json_data["objects"][-1]
        if last_object["type"] == "path" and len(last_object["path"]) >= 4:
            points = last_object["path"]
            dest_points = [(p[1] / scale, p[2] / scale) for p in points[:4]]

            os.makedirs("output2", exist_ok=True)
            out_path = os.path.join("output2", os.path.splitext(cap_filename)[0] + "_with_logo.png")

            applied = apply_logo_realistic(cap_path, st.session_state.logo_path, dest_points, out_path)
            if applied:
                st.image(applied, caption="Preview", width=400)

                if st.button("💾 Save Cap"):
                    ai_desc = ai_generate_description(placement, (st.session_state.w_cm, st.session_state.h_cm), cap_file.name)
                    st.session_state.results.append({
                        "image": cap_path,
                        "logo": st.session_state.logo_path,
                        "size_cm": (st.session_state.w_cm, st.session_state.h_cm),
                        "placement": placement,
                        "description": ai_desc,
                        "output": out_path,
                    })
                    st.success("Cap saved! Upload another image or generate report below.")

# --- FINAL REPORT ---
if st.session_state.results:
    st.markdown("---")
    st.header("Final Report")
    st.write(f"📦 You have added **{len(st.session_state.results)}** cap views so far.")

    cols = st.columns(min(len(st.session_state.results), 4))
    for i, result in enumerate(st.session_state.results):
        with cols[i % 4]:
            st.image(result["output"], caption=result["placement"], use_column_width=True)

    if st.button("📄 Generate PDF Report"):
        generate_pdf_report(st.session_state.results, "logo_techpack.pdf")
        with open("logo_techpack.pdf", "rb") as f:
            st.download_button("⬇️ Download Techpack PDF", f, file_name="logo_techpack.pdf")
