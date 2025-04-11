from flask import Flask, render_template, request, send_file, session, redirect, url_for, flash
import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers import RoundedModuleDrawer, GappedSquareModuleDrawer
from qrcode.image.styles.colormasks import RadialGradiantColorMask, SolidFillColorMask
from io import BytesIO
import os
import zipfile
import csv
from PIL import Image
from werkzeug.utils import secure_filename
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from datetime import timedelta



app = Flask(__name__)
app.secret_key = os.urandom(24)  # Needed for session
app.permanent_session_lifetime = timedelta(days=7)



def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate', methods=['GET', 'POST'])
def generate_qr():
    session.permanent = True
    if request.method == 'POST':
        # Support both JSON and form submission
        if request.is_json:
            content = request.get_json()
            data = content.get('data', '')
            fg_color = content.get('fg_color', '#000000')
            bg_color = content.get('bg_color', '#ffffff')
        else:
            data = request.form.get('qrdata', '')
            fg_color = request.form.get('fg_color', '#000000')
            bg_color = request.form.get('bg_color', '#ffffff')

        if not data:
            return "No data provided!", 400

        qr = qrcode.QRCode(box_size=10, border=4)
        qr.add_data(data)
        qr.make(fit=True)

        img = qr.make_image(fill_color=fg_color, back_color=bg_color)

        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)

        if 'history' not in session:
            session['history'] = []
        session['history'].append(data)
        session.modified = True

        return send_file(buffer, mimetype='image/png')

    return render_template('generate.html')



@app.route('/history')
def qr_history():
    history = session.get('history', [])
    return render_template('history.html', history=history[::-1])  # show most recent first


@app.route('/batch', methods=['GET', 'POST'])
def batch_qr():
    if request.method == 'POST':
        file = request.files.get('csv_file')
        if not file:
            flash("No file uploaded.", "error")
            return redirect(request.url)

        try:
            # Read CSV contents
            stream = BytesIO(file.read().decode('utf-8').encode())
            stream.seek(0)
            reader = csv.reader(stream.read().decode('utf-8').splitlines())

            # Create in-memory zip
            zip_buffer = BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for i, row in enumerate(reader):
                    if not row:
                        continue
                    data = row[0].strip()
                    if data:
                        img = qrcode.make(data)
                        img_buffer = BytesIO()
                        img.save(img_buffer, format='PNG')
                        img_buffer.seek(0)
                        zipf.writestr(f"qr_code_{i+1}.png", img_buffer.read())

            zip_buffer.seek(0)
            flash("QR codes generated successfully!", "success")
            return send_file(
                zip_buffer,
                mimetype='application/zip',
                as_attachment=True,
                download_name='qr_codes.zip'
            )
        except Exception as e:
            print(e)
            flash("Error processing CSV file.", "error")
            return redirect(request.url)

    return render_template("batch.html")

@app.route('/batch/upload', methods=['POST'])
def upload_csv():
    file = request.files.get('csv_file')
    if not file:
        return "No file uploaded", 400

    # Read file content into memory
    file_data = file.read()
    session['uploaded_csv'] = file_data
    return '', 200

@app.route('/batch/download', methods=['POST'])
def download_batch():
    file_data = session.get('uploaded_csv')
    if not file_data:
        return "No CSV uploaded", 400

    csv_io = BytesIO(file_data)
    reader = csv.reader(csv_io.read().decode('utf-8').splitlines())

    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
        for i, row in enumerate(reader):
            if not row:
                continue
            data = row[0]
            qr = qrcode.make(data)
            qr_io = BytesIO()
            qr.save(qr_io, format='PNG')
            qr_io.seek(0)
            zip_file.writestr(f"qr_code_{i+1}.png", qr_io.read())

    zip_buffer.seek(0)
    return send_file(zip_buffer, as_attachment=True, download_name='qr_codes.zip', mimetype='application/zip')

@app.route('/generate-pdf', methods=['POST'])
def generate_pdf():
    data = request.form.get('qrdata')
    if not data:
        return "No data provided!", 400

    # Generate QR Code using qrcode and Pillow
    qr_img = qrcode.make(data)
    qr_io = BytesIO()
    qr_img.save(qr_io, format='PNG')
    qr_io.seek(0)

    # Create a PDF and embed the QR code
    pdf_io = BytesIO()
    c = canvas.Canvas(pdf_io, pagesize=letter)

    # Convert BytesIO to Pillow Image for size info
    pil_img = Image.open(qr_io)
    width, height = pil_img.size

    # Save temp QR to embed in PDF
    qr_path = "temp_qr.png"
    pil_img.save(qr_path)

    # Embed into PDF (x=200, y=500 to center roughly)
    c.drawImage(qr_path, 200, 500, width=150, height=150)

    c.setFont("Helvetica", 12)
    c.drawString(200, 480, f"QR Code for: {data[:50]}...")

    c.save()
    pdf_io.seek(0)

    return send_file(
        pdf_io,
        mimetype='application/pdf',
        as_attachment=True,
        download_name='qr_code.pdf'
    )

@app.route('/scan')
def scan_qr():
    return render_template('scan.html')

@app.route('/contact')
def contact_qr():
    return render_template('contact.html')

if __name__ == '__main__':
    app.run(debug=True)
