import os
import markdown
from pyhtml2pdf import converter
from problem_list import problem_list

def save_memo():
    html_portion = markdown.markdown(f'## MEMO ✎')

    styled_html = f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <title>Document</title>
        <style>
            body {{
                font-family: 'Arial', sans-serif;
                margin: 40px;
                background-color: #ffffff; /* White background */
                color: #333366; /* Dark blue text */
            }}
            h2 {{
                color: #104061; /* Vibrant blue for headings */
                font-size: 20px;
                border-bottom: 1px solid #6f8695;
                border-top: 3px solid #6f8695;
                padding: 10px 0;
            }}
        </style>
    </head>
    <body>
        {html_portion}
    </body>
    </html>
    """
    os.makedirs(f'./data', exist_ok=True)
    with open(f'./data/memo.html', 'w') as file:
        file.write(styled_html)

    return styled_html

def save_pdf():
    path = os.path.abspath(f'data/memo.html')
    pdf_dir = os.path.dirname(path)
    os.makedirs(pdf_dir, exist_ok=True)
    converter.convert(f'file:///{path}', os.path.join(pdf_dir, 'memo.pdf'))

if __name__ == "__main__":
    save_memo()
    save_pdf()