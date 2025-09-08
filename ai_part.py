import os
import shutil
import cv2
import openai
import pandas as pd

# Pillow for image handling
from PIL import Image as PILImage

# ReportLab for PDF generation
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image as RLImage,
    Table, TableStyle, PageBreak
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# ----------------- CONFIG -----------------
UPLOAD_DIR = "uploads"
OUTPUT_DIR = "outputs"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

openai.api_key = os.getenv("OPENAI_API_KEY")  # Make sure this is set in your EC2 env


# ----------------- HELPERS -----------------
def save_uploaded_file(file_path):
    """Copy file into uploads/ folder and return its new path."""
    if not os.path.exists(file_path):
        print(f"⚠️ File not found: {file_path}")
        return None
    dest_path = os.path.join(UPLOAD_DIR, os.path.basename(file_path))
    shutil.copy(file_path, dest_path)
    return dest_path


def apply_logo(cap_image_path, logo_image_path, width, height, out_path):
    """Overlay logo onto cap image and save output."""
    try:
        cap_img = cv2.imread(cap_image_path)
        logo_img = cv2.imread(logo_image_path, cv2.IMREAD_UNCHANGED)

        if cap_img is None or logo_img is None:
            print("⚠️ Error: Could not load image(s).")
            return False

        # Resize logo
        logo_resized = cv2.resize(logo_img, (width, height))

        # Place logo at top-left (can be improved later)
        x, y = 50, 50
        y1, y2 = y, y + logo_resized.shape[0]
        x1, x2 = x, x + logo_resized.shape[1]

        # Handle alpha channel if exists
        if logo_resized.shape[2] == 4:
            alpha = logo_resized[:, :, 3] / 255.0
            for c in range(0, 3):
                cap_img[y1:y2, x1:x2, c] = (
                    alpha * logo_resized[:, :, c] + (1 - alpha) * cap_img[y1:y2, x1:x2, c]
                )
        else:
            cap_img[y1:y2, x1:x2] = logo_resized

        cv2.imwrite(out_path, cap_img)
        print(f"✅ Saved: {out_path}")
        return True
    except Exception as e:
        print(f"❌ Error applying logo: {e}")
        return False


def ai_generate_description(placement, size_cm, cap_name):
    """Use GPT to generate a short description."""
    try:
        prompt = f"Describe a logo placed on a {cap_name} at {placement}, size {size_cm[0]}x{size_cm[1]} cm."
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=60,
        )
        return response.choices[0].message["content"].strip()
    except Exception as e:
        print(f"⚠️ AI description failed: {e}")
        return f"Logo on {cap_name} at {placement}, size {size_cm[0]}x{size_cm[1]} cm."

def fetch_key_value_table(file_path, start_row=0, end_row=None, columns=None):
    """
    Reads Excel file and returns a list of lists suitable for ReportLab Table.
    
    columns format: {"indices": [col_idx1, col_idx2], "names": ["Detail", "Value"]}
    """
    df = pd.read_excel(file_path, header=None)
    df = df.iloc[start_row:end_row]
    
    if columns is None:
        cols_to_take = [0, 1]
        col_names = ["Column 1", "Column 2"]
    else:
        cols_to_take = columns.get("indices", [0, 1])
        col_names = columns.get("names", [f"Column {i+1}" for i in cols_to_take])
    
    subset = df.iloc[:, cols_to_take]
    subset.columns = col_names
    return subset.values.tolist()

# --- PDF Report ---
def generate_pdf_report(results, pdf_path="logo_techpack.pdf", excel_file=None, excel_columns=None, excel_start_row=0, excel_end_row=None):
    doc = SimpleDocTemplate(pdf_path, pagesize=A4)
    styles = getSampleStyleSheet()
    normal = ParagraphStyle("NormalWrap", parent=styles["Normal"], fontSize=10)
    heading = styles["Heading2"]

    story = []

    # Title
    story.append(Paragraph("<b>Trucker Hat Tech Pack</b>", styles["Title"]))
    story.append(Spacer(1, 20))

    story.append(Paragraph("<b>Design Summary</b>", styles["Title"]))
    story.append(Spacer(1, 12))

    # Fabric & Design Details (dynamic Excel)
    if excel_file and os.path.exists(excel_file):
        story.append(Paragraph("Fabric & Design Details", heading))
        story.append(Spacer(1, 12))
        try:
            design_data = fetch_key_value_table(
                excel_file, start_row=excel_start_row, end_row=excel_end_row, columns=excel_columns
            )
            design_table = Table(design_data, colWidths=[7*cm, 8*cm])
            design_table.setStyle(TableStyle([
                ('GRID', (0,0), (-1,-1), 0.5, colors.black),
                ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ]))
            story.append(design_table)
            story.append(Spacer(1, 20))
        except Exception as e:
            story.append(Paragraph(f"<b>⚠️ Error reading Excel file:</b> {str(e)}", normal))
            story.append(Spacer(1, 12))

    # Cap images
    for item in results:
        pil_img = PILImage.open(item["output"])
        w, h = pil_img.size
        aspect = w / h
        max_w, max_h = A4[0] - 4*cm, A4[1] - 8*cm

        if aspect > 1:
            display_w = max_w
            display_h = max_w / aspect
        else:
            display_h = max_h
            display_w = max_h * aspect

        story.append(RLImage(item["output"], width=display_w, height=display_h))
        story.append(Spacer(1, 6))

    # Measurements
    story.append(PageBreak())
    story.append(Paragraph("Design and Label Measurements", heading))
    story.append(Spacer(1, 12))
    story.append(Paragraph("Logo Placement Summary", heading))
    story.append(Spacer(1, 12))

    table_data = [["Logo", "Size (cm)", "Placement", "AI Description"]]
    for item in results:
        size_cm = f"{item['size_cm'][0]:.2f} × {item['size_cm'][1]:.2f} cm"
        logo_preview = RLImage(item["logo"], width=2*cm, height=2*cm)
        table_data.append([
            logo_preview,
            Paragraph(size_cm, normal),
            Paragraph(item["placement"], normal),
            Paragraph(item["description"], normal),
        ])

    meas_table = Table(table_data, colWidths=[3*cm, 3*cm, 4*cm, 6*cm])
    meas_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 1), (0, -1), 'CENTER'),
        ('ALIGN', (1, 1), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    story.append(meas_table)
    story.append(Spacer(1, 14))

    # Build PDF
    doc.build(story)
    print(f"📄 Techpack PDF saved as {pdf_path}")



# ----------------- MAIN -----------------
def main():
    results = []

    # --- Excel file input ---
    excel_file = input(ai_ask("📑 Enter path to your Excel file: ")).strip()
    if not os.path.exists(excel_file):
        print("⚠️ Excel file not found.")
        return
    try:
        start_row = int(input(ai_ask("Enter Excel start row (0-based index): ")))
        end_row = int(input(ai_ask("Enter Excel end row (exclusive): ")))
        col_indices = input(ai_ask("Enter Excel column indices (comma separated, e.g., 1,2): "))
        col_names = input(ai_ask("Enter names for these columns (comma separated): "))

        col_indices = [int(x.strip()) for x in col_indices.split(",")]
        col_names = [x.strip() for x in col_names.split(",")]
        excel_columns = {"indices": col_indices, "names": col_names}
    except Exception:
        print("⚠️ Invalid Excel input. Using defaults.")
        start_row, end_row, excel_columns = 0, None, None

    while True:
        # --- Logo input ---
        logo_path = input("🖼️ Enter path to your logo image: ").strip()
        logo_path = save_uploaded_file(logo_path)
        if not logo_path:
            continue

        # --- Cap/base image input ---
        cap_path = input("🧢 Enter path to the cap/base image: ").strip()
        cap_path = save_uploaded_file(cap_path)
        if not cap_path:
            continue

        # --- Logo size input ---
        try:
            size_in = input("👉 Enter logo width and height (cm, separated by space): ")
            w_cm, h_cm = map(float, size_in.split())
            w, h = int(w_cm * 37.8), int(h_cm * 37.8)  # 37.8 px/cm approx
        except Exception:
            print("⚠️ Invalid size. Using 3×3 cm.")
            w_cm, h_cm = 3, 3
            w, h = int(3 * 37.8), int(3 * 37.8)

        placement = input("📍 Where should I place the logo? (front, side, back, etc.): ").strip()

        out_path = os.path.join(
            OUTPUT_DIR,
            os.path.splitext(os.path.basename(cap_path))[0] + "_with_logo.png"
        )

        applied = apply_logo(cap_path, logo_path, w, h, out_path)
        if applied:
            ai_desc = ai_generate_description(placement, (w_cm, h_cm), os.path.basename(cap_path))
            results.append({
                "image": cap_path,
                "logo": logo_path,
                "size_cm": (w_cm, h_cm),
                "placement": placement,
                "description": ai_desc,
                "output": out_path,
            })

        cont = input("➕ Do you want to add another logo? (yes/no): ").strip().lower()
        if cont != "yes":
            break

    if results:
        pdf_out = os.path.join(OUTPUT_DIR, "logo_techpack.pdf")
        generate_pdf_report(results,excel_file=excel_file,excel_start_row=start_row,excel_end_row=end_row,excel_columns=excel_columns,pdf_path=os.path.join(out_dir, "logo_techpack_dynamic.pdf"))
    else:
        print("⚠️ No logos applied. Nothing to export.")


if __name__ == "__main__":
    main()








