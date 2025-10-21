from flask import Flask, render_template, request, send_from_directory, redirect, url_for
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from PyPDF2 import PdfReader, PdfWriter
import os
from io import BytesIO
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
import logging

# ---------------- Logger Setup ----------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

CARDS_FOLDER = "static/cards"
os.makedirs(CARDS_FOLDER, exist_ok=True)

# NOTE: This should point to the PDF template you've already created from the edited image.
TEMPLATE_PATH = "Farewell_Card.pdf"
#ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")


# Get password settings from environment
# Two supported environment variables:
# - ADMIN_PASSWORD_HASH : if you already stored a hashed password (recommended)
# - ADMIN_PASSWORD      : plain password (only for first-run convenience; will be hashed in-memory)
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH")

# If only a plain ADMIN_PASSWORD is provided, generate a secure hash in memory.
# If ADMIN_PASSWORD_HASH is provided, prefer that (assume it's already a PBKDF2/sha256 hash).
if ADMIN_PASSWORD_HASH:
    # Use the provided hash
    print("Using ADMIN_PASSWORD_HASH from environment.")
else:
    if ADMIN_PASSWORD:
        # If the ADMIN_PASSWORD looks like a werkzeug/pbkdf2 hash already, treat it as a hash.
        # Werkzeug generate_password_hash uses format: "pbkdf2:sha256:iterations$<salt>$<hash>"
        if ADMIN_PASSWORD.startswith("pbkdf2:sha256:"):
            ADMIN_PASSWORD_HASH = ADMIN_PASSWORD
            ADMIN_PASSWORD = None
            print("ADMIN_PASSWORD in env appears to already be a pbkdf2 hash; using it as ADMIN_PASSWORD_HASH.")
        else:
            # Generate a salted PBKDF2 SHA256 hash in memory
            ADMIN_PASSWORD_HASH = generate_password_hash(ADMIN_PASSWORD, method="pbkdf2:sha256", salt_length=16)
            # It's safer to unset plain password from memory
            ADMIN_PASSWORD = None
            print("Generated in-memory ADMIN_PASSWORD_HASH from ADMIN_PASSWORD. For permanent storage, set ADMIN_PASSWORD_HASH in your .env.")
    else:
        # Neither provided
        ADMIN_PASSWORD_HASH = None
        logger.warning("No ADMIN_PASSWORD or ADMIN_PASSWORD_HASH found in environment. Admin login will not work until this is set.")







@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        message = request.form.get("message", "").strip()
        
        MAX_MESSAGE_CHARS = 2000  # Limit to prevent overflowing the card

        if not name or not message:
            return render_template("index.html", error="Please enter both name and message.")
        
        if len(message) > MAX_MESSAGE_CHARS:
            return render_template("index.html", error=f"Message is too long. Please limit it to {MAX_MESSAGE_CHARS} characters.")

        output_filename = f"{name.replace(' ', '_').replace('/', '_')}_farewell_card.pdf"
        output_path = os.path.join(CARDS_FOLDER, output_filename)

        try:
            template_pdf = PdfReader(TEMPLATE_PATH)
            template_page = template_pdf.pages[0]
            
            page_width = template_page.mediabox.width
            page_height = template_page.mediabox.height
            page_size = (page_width, page_height)

            packet = BytesIO()
            c = canvas.Canvas(packet, pagesize=page_size)
            c.setFillColor(colors.HexColor('#2C3E50'))  # Text color

            # -------- Coordinates Tuned to Fit Box in Template --------
            message_left = 230       # left X start inside the box
            message_right = 670      # right limit of box text
            message_top = 700        # top Y start of box
            message_bottom = 220     # bottom Y limit inside box
            message_center_x = (message_left + message_right) / 2
            max_width = message_right - message_left
            line_height = 18         # spacing between lines

            c.setFont("Helvetica", 12)

            # ✅ Preserve line breaks entered by the user
            paragraphs = message.splitlines()
            lines = []

            for paragraph in paragraphs:
                words = paragraph.split()
                current_line = ""
                for word in words:
                    test_line = current_line + word + " "
                    if c.stringWidth(test_line, "Helvetica", 12) < max_width:
                        current_line = test_line
                    else:
                        if current_line:
                            lines.append(current_line.strip())
                        current_line = word + " "
                if current_line:
                    lines.append(current_line.strip())
                # Add a blank line for paragraph break
                #lines.append("")

            max_lines = int((message_top - message_bottom) / line_height)

            for i, line in enumerate(lines[:max_lines]):
                current_y = message_top - (i * line_height)
                if current_y < message_bottom:
                    break
                c.drawString(message_left, current_y, line)

            # -------- Name Section --------
            if lines:
                last_line_y = message_top - ((len(lines[:max_lines]) - 1) * line_height)
                name_y = last_line_y - 25  # Dynamic close spacing
            else:
                name_y = 200  # Fallback if no message lines drawn

            name_text = f"- {name}"
            c.setFont("Helvetica-Bold", 14)
            name_width = c.stringWidth(name_text, "Helvetica-Bold", 14)
            name_x = message_right - name_width - 10
            c.drawString(name_x, name_y, name_text)

            c.save()
            packet.seek(0)

            overlay_pdf = PdfReader(packet)
            overlay_page = overlay_pdf.pages[0]
            template_page.merge_page(overlay_page)

            writer = PdfWriter()
            writer.add_page(template_page)

            with open(output_path, "wb") as f:
                writer.write(f)

            return redirect(url_for("index"))

        except FileNotFoundError:
            return render_template("index.html", error=f"Error: Required PDF template '{TEMPLATE_PATH}' not found.")
        except Exception as e:
            return render_template("index.html", error=f"Error generating PDF. Details: {str(e)}")

    cards = sorted([f for f in os.listdir(CARDS_FOLDER) if f.endswith('.pdf')])
    return render_template("index.html", cards=cards)

@app.route("/cards/<filename>")
def get_card(filename):
    return send_from_directory(CARDS_FOLDER, filename)

@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST":
        password = request.form.get("password", "")
        if password != ADMIN_PASSWORD:
            return render_template("admin.html", error="Invalid password.")
        cards = sorted([f for f in os.listdir(CARDS_FOLDER) if f.endswith('.pdf')])
        return render_template("admin.html", cards=cards, authorized=True)
    return render_template("admin.html")

@app.route("/delete/<filename>", methods=["POST"])
def delete_card(filename):
    filepath = os.path.join(CARDS_FOLDER, filename)
    if os.path.exists(filepath) and os.path.isfile(filepath) and os.path.dirname(filepath) == CARDS_FOLDER:
        os.remove(filepath)
    return redirect(url_for("admin"))

if __name__ == "__main__":
    app.run(debug=True)


















# Code without linebreaks
# from flask import Flask, render_template, request, send_from_directory, redirect, url_for
# from reportlab.pdfgen import canvas
# from reportlab.lib import colors
# from PyPDF2 import PdfReader, PdfWriter
# import os
# from io import BytesIO

# app = Flask(__name__)

# CARDS_FOLDER = "static/cards"
# os.makedirs(CARDS_FOLDER, exist_ok=True)

# # NOTE: This should point to the PDF template you've already created from the edited image.
# TEMPLATE_PATH = "Farewell_Card.pdf"
# ADMIN_PASSWORD = "admin123"

# @app.route("/", methods=["GET", "POST"])
# def index():
#     if request.method == "POST":
#         name = request.form.get("name", "").strip()
#         message = request.form.get("message", "").strip()
        
#         MAX_MESSAGE_CHARS = 2000  # Limit to prevent overflowing the card

#         if not name or not message:
#             return render_template("index.html", error="Please enter both name and message.")
        
#         if len(message) > MAX_MESSAGE_CHARS:
#             return render_template("index.html", error=f"Message is too long. Please limit it to {MAX_MESSAGE_CHARS} characters.")

#         output_filename = f"{name.replace(' ', '_').replace('/', '_')}_farewell_card.pdf"
#         output_path = os.path.join(CARDS_FOLDER, output_filename)

#         try:
#             template_pdf = PdfReader(TEMPLATE_PATH)
#             template_page = template_pdf.pages[0]
            
#             page_width = template_page.mediabox.width
#             page_height = template_page.mediabox.height
#             page_size = (page_width, page_height)

#             packet = BytesIO()
#             c = canvas.Canvas(packet, pagesize=page_size)
#             c.setFillColor(colors.HexColor('#2C3E50'))  # Text color

#             # -------- Coordinates Tuned to Fit Box in Template --------
#             # Adjusted by checking the actual bounding box area visually.
#             # Message area (inside the box)
#             message_left = 230       # left X start inside the box
#             message_right = 670     # right limit of box text
#             message_top = 700       # top Y start of box
#             message_bottom = 220    # bottom Y limit inside box
#             message_center_x = (message_left + message_right) / 2
#             max_width = message_right - message_left
#             line_height = 18        # spacing between lines

#             c.setFont("Helvetica", 12)
#             words = message.split()
#             lines = []
#             current_line = ""

#             for word in words:
#                 test_line = current_line + word + " "
#                 if c.stringWidth(test_line, "Helvetica", 12) < max_width:
#                     current_line = test_line
#                 else:
#                     if current_line:
#                         lines.append(current_line.strip())
#                     current_line = word + " "
#             if current_line:
#                 lines.append(current_line.strip())

#             max_lines = int((message_top - message_bottom) / line_height)

#             for i, line in enumerate(lines[:max_lines]):
#                 current_y = message_top - (i * line_height)
#                 if current_y < message_bottom:
#                     break
#                 c.drawString(message_left, current_y, line)

#             # -------- Name Section --------
#             # Centered horizontally closer under the message box
#             # Reduced gap between last message line and name
#             if lines:
#                 last_line_y = message_top - ((len(lines[:max_lines]) - 1) * line_height)
#                 name_y = last_line_y - 25  # Reduced from 190 → dynamic close spacing
#             else:
#                 name_y = 200  # Fallback if no message lines drawn

#             name_text = f"- {name}"
#             c.setFont("Helvetica-Bold", 14)
#             name_width = c.stringWidth(name_text, "Helvetica-Bold", 14)
#             # draw at right side instead of center
#             name_x = message_right - name_width - 10
#             c.drawString(name_x, name_y, name_text)
#             #c.drawString(message_center_x - (name_width / 2), name_y, name_text)

#             c.save()
#             packet.seek(0)

#             overlay_pdf = PdfReader(packet)
#             overlay_page = overlay_pdf.pages[0]

#             template_page.merge_page(overlay_page)

#             writer = PdfWriter()
#             writer.add_page(template_page)

#             with open(output_path, "wb") as f:
#                 writer.write(f)

#             return redirect(url_for("index"))

#         except FileNotFoundError:
#             return render_template("index.html", error=f"Error: Required PDF template '{TEMPLATE_PATH}' not found.")
#         except Exception as e:
#             return render_template("index.html", error=f"Error generating PDF. Details: {str(e)}")

#     cards = sorted([f for f in os.listdir(CARDS_FOLDER) if f.endswith('.pdf')])
#     return render_template("index.html", cards=cards)

# @app.route("/cards/<filename>")
# def get_card(filename):
#     return send_from_directory(CARDS_FOLDER, filename)

# @app.route("/admin", methods=["GET", "POST"])
# def admin():
#     if request.method == "POST":
#         password = request.form.get("password", "")
#         if password != ADMIN_PASSWORD:
#             return render_template("admin.html", error="Invalid password.")
#         cards = sorted([f for f in os.listdir(CARDS_FOLDER) if f.endswith('.pdf')])
#         return render_template("admin.html", cards=cards, authorized=True)
#     return render_template("admin.html")

# @app.route("/delete/<filename>", methods=["POST"])
# def delete_card(filename):
#     filepath = os.path.join(CARDS_FOLDER, filename)
#     if os.path.exists(filepath) and os.path.isfile(filepath) and os.path.dirname(filepath) == CARDS_FOLDER:
#         os.remove(filepath)
#     return redirect(url_for("admin"))

# if __name__ == "__main__":
#     app.run(debug=True)
































# from flask import Flask, render_template, request, send_from_directory, redirect, url_for
# from reportlab.pdfgen import canvas
# from reportlab.lib.pagesizes import letter
# from reportlab.lib import colors
# from PyPDF2 import PdfReader, PdfWriter
# import os
# from io import BytesIO

# app = Flask(__name__)

# # Folder to save generated cards
# CARDS_FOLDER = "static/cards"
# os.makedirs(CARDS_FOLDER, exist_ok=True)

# # Path to the editable template
# TEMPLATE_PATH = "farewell_card_editable.pdf"

# # Simple admin password (change this!)
# ADMIN_PASSWORD = "admin123"


# @app.route("/", methods=["GET", "POST"])
# def index():
#     if request.method == "POST":
#         name = request.form.get("name", "").strip()
#         message = request.form.get("message", "").strip()

#         if not name or not message:
#             return render_template("index.html", error="Please enter both name and message.")

#         output_filename = f"{name.replace(' ', '_')}_farewell_card.pdf"
#         output_path = os.path.join(CARDS_FOLDER, output_filename)

#         try:
#             # Read the template
#             template_pdf = PdfReader(TEMPLATE_PATH)
#             template_page = template_pdf.pages[0]
#             page_width = float(template_page.mediabox.width)
#             page_height = float(template_page.mediabox.height)

#             # Create overlay PDF with the message and name
#             packet = BytesIO()
#             c = canvas.Canvas(packet, pagesize=(page_width, page_height))

#             # Text colour
#             c.setFillColor(colors.HexColor('#8B7355'))

#             # ---------- MESSAGE ----------
#             c.setFont("Helvetica", 11)
#             max_width = 270
#             words = message.split()
#             lines = []
#             current_line = ""

#             for word in words:
#                 test_line = current_line + word + " "
#                 if c.stringWidth(test_line, "Helvetica", 11) < max_width:
#                     current_line = test_line
#                 else:
#                     if current_line:
#                         lines.append(current_line.strip())
#                     current_line = word + " "
#             if current_line:
#                 lines.append(current_line.strip())

#             y_start = 495
#             line_height = 18
#             for i, line in enumerate(lines[:12]):  # limit to 12 lines
#                 c.drawString(195, y_start - i * line_height, line)

#             # ---------- NAME ----------
#             c.drawString(260, 175, name)

#             c.save()
#             packet.seek(0)

#             # Merge: put template behind the overlay so text is visible
#             overlay_pdf = PdfReader(packet)
#             overlay_page = overlay_pdf.pages[0]
#             overlay_page.merge_page(template_page)

#             writer = PdfWriter()
#             writer.add_page(overlay_page)

#             with open(output_path, "wb") as f:
#                 writer.write(f)

#             return redirect(url_for("index"))

#         except Exception as e:
#             return render_template("index.html", error=f"Error generating PDF: {str(e)}")

#     # List existing cards
#     cards = sorted([f for f in os.listdir(CARDS_FOLDER) if f.endswith('.pdf')])
#     return render_template("index.html", cards=cards)


# @app.route("/cards/<filename>")
# def get_card(filename):
#     return send_from_directory(CARDS_FOLDER, filename)


# @app.route("/admin", methods=["GET", "POST"])
# def admin():
#     if request.method == "POST":
#         password = request.form.get("password", "")
#         if password != ADMIN_PASSWORD:
#             return render_template("admin.html", error="Invalid password.")
#         cards = sorted([f for f in os.listdir(CARDS_FOLDER) if f.endswith('.pdf')])
#         return render_template("admin.html", cards=cards, authorized=True)
#     return render_template("admin.html")


# @app.route("/delete/<filename>", methods=["POST"])
# def delete_card(filename):
#     filepath = os.path.join(CARDS_FOLDER, filename)
#     if os.path.exists(filepath):
#         os.remove(filepath)
#     return redirect(url_for("admin"))


# if __name__ == "__main__":
#     app.run(debug=True)