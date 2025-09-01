import os
import streamlit as st
from streamlit_drawable_canvas import st_canvas
from PIL import Image
from ai_part import ai_generate_description, generate_pdf_report
import numpy as np
import pandas as pd
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
    Image as RLImage, PageBreak
)
from reportlab.lib.units import cm
import os
import sys
from PIL import Image
import matplotlib.pyplot as plt
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
    Image as RLImage, PageBreak
)
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from openai import OpenAI
import pandas as pd



# --- Utility functions ---
@st.cache_data(show_spinner=False)
def resize_logo(logo_path, width_px, height_px):
    logo_img = Image.open(logo_path).convert("RGBA")
    return logo_img.resize((width_px, height_px))

@st.cache_data(show_spinner=False)
def load_image(path):
    return Image.open(path).convert("RGBA")

def apply_logo(cap_path, logo_path, width_px, height_px, out_path, center):
    logo_resized = resize_logo(logo_path, width_px, height_px)
    cx, cy = center
    w, h = logo_resized.size
    pos = (int(cx - w/2), int(cy - h/2))

    cap_img = load_image(cap_path)
    composite = cap_img.copy()
    composite.paste(logo_resized, pos, logo_resized)
    composite.save(out_path)
    return out_path

def fetch_key_value_table(file_path, start_row, end_row, column1, column2):
    df = pd.read_excel(file_path, header=None)
    subset = df.iloc[start_row-1:end_row, [1, 2]].dropna()
    subset.columns = [column1, column2]
    return subset.values.tolist()

# --- Streamlit App ---
st.set_page_config(page_title="Logo Placement Tool", layout="wide")
st.title("🧢 Tech Pack Logo Placement Tool")

# --- Session state ---
if "results" not in st.session_state:
    st.session_state.results = []
if "logo_path" not in st.session_state:
    st.session_state.logo_path = None
if "w_cm" not in st.session_state:
    st.session_state.w_cm = 3.0
if "h_cm" not in st.session_state:
    st.session_state.h_cm = 3.0
if "retry" not in st.session_state:
    st.session_state.retry = False


st.subheader("Step 0: Upload Excel & Select Data Range")

excel_file = st.file_uploader("Upload Excel File", type=["xlsx", "xls"], key="excel_upload")

if excel_file:
    # Don’t assign headers yet (so we can rename freely)
    df = pd.read_excel(excel_file, header=None)

    total_rows = len(df)
    st.write(f"📊 Total rows detected: {total_rows}")

    # --- User inputs ---
    key_col_input = st.text_input("Enter column name for Keys (renamed)").strip()
    value_col_input = st.text_input("Enter column name for Values (renamed)").strip()

    start_row = st.number_input("Start Row (1-indexed)", min_value=1, max_value=total_rows, value=1, step=1)
    end_row = st.number_input("End Row (1-indexed)", min_value=1, max_value=total_rows, value=total_rows, step=1)

    if st.button("📥 Fetch Data from Excel"):
        # Take columns 1 and 2 (i.e. B and C in Excel, since Python is 0-based)
        subset = df.iloc[start_row-1:end_row, [1, 2]].dropna()

        # Rename columns to user input
        if key_col_input and value_col_input:
            subset.columns = [key_col_input, value_col_input]
        else:
            subset.columns = ["Key", "Value"]

        st.success(f"✅ Fetched {len(subset)} rows.")
        st.dataframe(subset)

        # Example: also show how you’d pass to a ReportLab table
        design_data = subset.values.tolist()
        design_table = Table(design_data, colWidths=[7*cm, 8*cm])
        design_table.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ]))
        st.info("Table ready for PDF export ✅")



# --- Step 1: Upload logo ---
st.subheader("Step 1: Upload Logo Image")
logo_file = st.file_uploader("Upload Logo Image", type=["png", "jpg", "jpeg"], key="logo_upload")

if logo_file and (st.session_state.logo_path is None or os.path.basename(st.session_state.logo_path) != logo_file.name):
    os.makedirs("uploads", exist_ok=True)
    logo_path = os.path.join("uploads", logo_file.name)
    logo = Image.open(logo_file).convert("RGBA")
    if logo_path.lower().endswith((".jpg", ".jpeg")):
        logo.convert("RGB").save(logo_path)
    else:
        logo.save(logo_path)
    st.session_state.logo_path = logo_path
    st.success("✅ Logo uploaded.")


# --- Step 2: Choose Logo Size ---
st.subheader("Step 2: Choose Logo Size")
col_w, col_h = st.columns(2)
with col_w:
    st.session_state.w_cm = st.number_input("Width (cm)", min_value=1.0, value=st.session_state.w_cm, step=0.5)
with col_h:
    st.session_state.h_cm = st.number_input("Height (cm)", min_value=1.0, value=st.session_state.h_cm, step=0.5)

w_px, h_px = int(st.session_state.w_cm * 37.8), int(st.session_state.h_cm * 37.8)


# --- Step 3: Upload and Place Logo ---
st.subheader("Step 3: Upload and Place Logo on Cap")
cap_file = st.file_uploader(
    "Upload Cap/Base Image",
    type=["png", "jpg", "jpeg"],
    key=f"cap_{len(st.session_state.results)}"
)

if cap_file:
    # Save cap only once
    cap_path = os.path.join("uploads", cap_file.name)
    if not os.path.exists(cap_path):
        os.makedirs("uploads", exist_ok=True)
        cap = Image.open(cap_file).convert("RGBA")
        if cap_path.lower().endswith((".jpg", ".jpeg")):
            cap.convert("RGB").save(cap_path)
        else:
            cap.save(cap_path)
    else:
        cap = load_image(cap_path)

    # Resize for display only
    max_width = 400
    scale = max_width / cap.width
    new_size = (max_width, int(cap.height * scale))
    cap_resized = cap.resize(new_size)

    canvas_result = st_canvas(
        fill_color="rgba(0, 0, 0, 0)",
        stroke_width=1,
        stroke_color="red",
        background_image=cap_resized,
        update_streamlit=True,
        height=cap_resized.height,
        width=cap_resized.width,
        drawing_mode="point",
        key=f"canvas_{len(st.session_state.results)}",
    )

    if canvas_result.json_data and canvas_result.json_data["objects"]:
        obj = canvas_result.json_data["objects"][-1]
        cx_resized, cy_resized = int(obj["left"]), int(obj["top"])
        cx = int(cx_resized / scale)
        cy = int(cy_resized / scale)

        st.success(f"✅ Placement selected at ({cx}, {cy})")

        # Apply logo only if uploaded
        if st.session_state.logo_path:
            os.makedirs("output1", exist_ok=True)
            out_path = os.path.join("output1", os.path.splitext(cap_file.name)[0] + "_with_logo.png")

            applied = apply_logo(cap_path, st.session_state.logo_path, w_px, h_px, out_path, center=(cx, cy))
            img = Image.open(applied)
            img.thumbnail((400, 400))
            st.image(img, caption="Cap with Logo")

            placement = st.text_input("Placement description (front, side, back, etc.)", "front", key=f"placement_{len(st.session_state.results)}")
            ai_desc = ai_generate_description(placement, (st.session_state.w_cm, st.session_state.h_cm), cap_file.name)

            col1, col2 = st.columns(2)
            with col1:
                if st.button("🔄 Retry", key=f"retry_{len(st.session_state.results)}"):
                    st.session_state.retry = True
                    st.experimental_rerun()
            with col2:
                if st.button("✅ Save This Cap", key=f"save_{len(st.session_state.results)}"):
                    st.session_state.results.append({
                        "image": cap_path,
                        "logo": st.session_state.logo_path,
                        "size_cm": (st.session_state.w_cm, st.session_state.h_cm),
                        "placement": placement,
                        "description": ai_desc,
                        "output": out_path,
                    })
                    st.success("Cap saved! Now you can add another or finish.")


# --- Step 4: Finalize ---
if st.session_state.results:
    st.markdown("---")
    st.write(f"📦 You have added **{len(st.session_state.results)} caps** so far.")
    if st.button("➕ Add Another Cap"):
        st.experimental_rerun()
    if st.button("📄 Generate PDF Report"):
        generate_pdf_report(st.session_state.results, "logo_techpack.pdf")
        with open("logo_techpack.pdf", "rb") as f:
            st.download_button("⬇️ Download Techpack PDF", f, file_name="logo_techpack.pdf")

