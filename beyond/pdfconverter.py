import pdfkit

# Path to your local HTML file
html_file = './problems/simulation/13567.html'

# Path where you want to save the PDF
output_pdf = './problems/simulation/13567.pdf'

# Convert HTML to PDF
pdfkit.from_file(html_file, output_pdf, options={"no-stop-slow-scripts": "", "disable-smart-shrinking": ""})


print(f'PDF saved to {output_pdf}')
