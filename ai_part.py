import os
import shutil
import cv2
import openai
import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

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


def generate_pdf_report(results, pdf_path):
    """Generate a PDF techpack report."""
    c = canvas.Canvas(pdf_path, pagesize=A4)
    width, height = A4

    c.setFont("Helvetica-Bold", 16)
    c.drawString(2 * cm, height - 2 * cm, "Logo Techpack Report")

    y = height - 3 * cm
    for r in results:
        c.setFont("Helvetica", 12)
        c.drawString(2 * cm, y, f"Placement: {r['placement']} | Size: {r['size_cm']} cm")
        y -= 0.5 * cm
        c.drawString(2 * cm, y, f"Description: {r['description']}")
        y -= 1.5 * cm

        try:
            c.drawImage(r["output"], 2 * cm, y - 6 * cm, width=8 * cm, preserveAspectRatio=True)
            y -= 7 * cm
        except Exception as e:
            print(f"⚠️ Could not add image to PDF: {e}")

        if y < 5 * cm:
            c.showPage()
            y = height - 3 * cm

    c.save()
    print(f"📄 PDF saved: {pdf_path}")


# ----------------- MAIN -----------------
def main():
    results = []

    # --- Excel file input ---
    excel_path = input("📑 Enter path to your Excel (e.g., TECH.xlsx): ").strip()
    excel_path = save_uploaded_file(excel_path)
    if not excel_path:
        print("❌ Excel file is required to generate PDF.")
        return

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
        generate_pdf_report(results, pdf_out)
    else:
        print("⚠️ No logos applied. Nothing to export.")


if __name__ == "__main__":
    main()
