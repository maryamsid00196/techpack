# --- PAGE CONFIG ---
import streamlit as st
st.set_page_config(page_title="Logo Placement Tool", layout="wide")

# --- INIT SESSION ---
defaults = {
    "results": [],
    "logo_path": None,
    "w_cm": 5.0,
    "h_cm": 5.0,
    "cap_images": {},
    "canvas_objects": {},
    "placement": "Front Panel",
    "current_cap_filename": None,
    "canvas_json": None,
    "preview_image_path": None,
    "excel_data": None,
}
for k, v in defaults.items():
    st.session_state.setdefault(k, v)

# --- IMPORTS ---
import os
import pandas as pd
from PIL import Image
from streamlit_drawable_canvas import st_canvas
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import Table, TableStyle

from ai_part import ai_generate_description, generate_pdf_report
from opencv_logic import apply_logo_realistic


# --- STEP 0: UPLOAD EXCEL ---
st.subheader("Step 0: Upload Excel File")
excel_file = st.file_uploader("Upload Excel", type=["xlsx", "xls"])
if excel_file:
    st.session_state.excel_data = pd.read_excel(excel_file, header=None)
    st.success("Excel uploaded.")

# --- STEP 1: UPLOAD LOGO ---
st.subheader("Step 1: Upload Logo Image")
logo_file = st.file_uploader("Upload Logo", type=["png", "jpg", "jpeg"])
if logo_file:
    os.makedirs("uploads", exist_ok=True)
    logo_path = os.path.join("uploads", f"logo_{logo_file.name}")
    Image.open(logo_file).save(logo_path)
    st.session_state.logo_path = logo_path
    st.success("Logo uploaded.")

# --- STEP 2: SIZE INPUT ---
st.subheader("Step 2: Logo Size")
st.session_state.w_cm = st.number_input("Width (cm)", 1.0, 20.0, st.session_state.w_cm)
st.session_state.h_cm = st.number_input("Height (cm)", 1.0, 20.0, st.session_state.h_cm)

# --- STEP 3: UPLOAD CAP IMAGE ---
st.subheader("Step 3: Upload Cap/Base Image")
cap_file = st.file_uploader("Upload Cap Image", type=["png", "jpg", "jpeg"])
if cap_file:
    cap_path = os.path.join("uploads", f"cap_{cap_file.name}")
    Image.open(cap_file).save(cap_path)
    st.session_state.current_cap_filename = os.path.basename(cap_path)
    st.session_state.cap_images[st.session_state.current_cap_filename] = cap_path
    st.success("Cap image uploaded.")

# --- CANVAS (optional placement) ---
if st.session_state.current_cap_filename:
    cap_img = Image.open(st.session_state.cap_images[st.session_state.current_cap_filename])
    display_size = (600, int(cap_img.height * 600 / cap_img.width))
    canvas_result = st_canvas(
        fill_color="rgba(255, 165, 0, 0.3)",
        stroke_width=2,
        stroke_color="red",
        background_image=cap_img.resize(display_size),
        height=display_size[1],
        width=display_size[0],
        drawing_mode="polygon",
        key="canvas_main",
    )
    if canvas_result.json_data:
        st.session_state.canvas_json = canvas_result.json_data

# --- FINAL RUN BUTTON ---
st.markdown("---")
if st.button("▶️ Run Process"):
    if not st.session_state.logo_path or not st.session_state.current_cap_filename:
        st.error("Please upload both logo and cap image.")
    else:
        cap_path = st.session_state.cap_images[st.session_state.current_cap_filename]
        logo_path = st.session_state.logo_path
        json_data = st.session_state.canvas_json

        if json_data and json_data.get("objects"):
            points = json_data["objects"][-1]["path"]
            dest_points = [(p[1], p[2]) for p in points[:4]]

            os.makedirs("output2", exist_ok=True)
            out_path = os.path.join("output2", "preview.png")

            if apply_logo_realistic(cap_path, logo_path, dest_points, out_path):
                st.session_state.preview_image_path = out_path

                ai_desc = ai_generate_description(
                    st.session_state.placement,
                    (st.session_state.w_cm, st.session_state.h_cm),
                    st.session_state.current_cap_filename,
                )
                st.session_state.results.append({
                    "image": cap_path,
                    "logo": logo_path,
                    "size_cm": (st.session_state.w_cm, st.session_state.h_cm),
                    "placement": st.session_state.placement,
                    "description": ai_desc,
                    "output": out_path,
                })
                st.success("Processing complete.")

# --- PREVIEW & REPORT ---
if st.session_state.results:
    st.header("Results")
    for res in st.session_state.results:
        st.image(res["output"], caption=res["placement"], width=300)

    if st.button("📄 Generate PDF"):
        generate_pdf_report(st.session_state.results, "logo_techpack.pdf")
        with open("logo_techpack.pdf", "rb") as f:
            st.download_button("⬇️ Download PDF", f, file_name="logo_techpack.pdf")
