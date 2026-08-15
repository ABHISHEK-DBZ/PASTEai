from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

c = canvas.Canvas("sample_datasheet.pdf", pagesize=letter)
c.setFont("Helvetica", 14)
y = 720
lines = [
    "Industrial Motor - Model X-100",
    "Voltage Rating: 220V AC",
    "Current Rating: 4.5A",
    "Power Rating: 0.75 kW",
    "Frequency: 50 Hz",
    "IP Rating: IP65",
    "Operating Temperature: -20 to 70C",
    "Weight: 12 kg",
    "Manufacturer: Acme Industrial",
    "Certifications: CE, UL",
]
for line in lines:
    c.drawString(72, y, line)
    y -= 24
c.save()
print("wrote sample_datasheet.pdf")
