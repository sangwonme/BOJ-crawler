import html2text
import requests
import os
from bs4 import BeautifulSoup
import json
import markdown
from problem_list import problem_list

def getBOJHTML(problemID):

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.77 Safari/537.36'
    }

    comp_code = []  # comparison code
    fetch_problem = []  # fetch problem dynamically

    comp_code.append(problemID)
    fetch_problem.append('<a href="/problem/{0}"></a>'.format(comp_code[0]))
    fetch_problem = (''.join(list(map(str, fetch_problem))))  # Change to string type

    integer_comp_code = int(comp_code[0])  # Integer comp code
    problem_url = 'https://www.acmicpc.net/problem/'
    merged_url = problem_url + str(integer_comp_code)  # Integer.
    responses = requests.get(merged_url, headers=headers)


    if responses.status_code == 200:
        html = responses.text
        return (html)
    
def save_page_md(problem_id, id, html):
    # Parse the HTML content
    soup = BeautifulSoup(html, 'html.parser')

    # title
    title = soup.find('span', id='problem_title').text
    level = requests.get(f'https://solved.ac/api/v3/problem/show?problemId={problem_id}').text
    level = json.loads(level)['level']
    star = (level-1)//5 + 1

    # Extract content under div#problem_description
    problem_description = soup.find('div', id='problem_description')
    input_description = soup.find('section', id='input')
    output_description = soup.find('section', id='output')

    # Count Sample I/O num
    sample_io_num = 1
    while True:
        tmp = soup.find('section', id=f'sampleinput{sample_io_num}')
        if tmp:
            sample_io_num += 1
        else:
            break
    
    # get sample_io
    sample_io = []
    for i in range(1, sample_io_num+1):
        sample_io.append(soup.find('section', id=f'sampleinput{i}'))
        sample_io.append(soup.find('section', id=f'sampleoutput{i}'))

    # Initialize html2text converter
    h = html2text.HTML2Text()
    h.ignore_links = False

    # Convert HTML elements to Markdown and concatenate them
    markdown_content = f"# {id}. {title} {'★'*star + '☆'*(3-star)}\n"
    for element in [problem_description, input_description, output_description]:
        if element:
            markdown_content += h.handle(str(element))

    for element in sample_io:
        if element:
            markdown_content += h.handle(str(element).replace('복사', ''))

    return markdown_content

def save_page_html(chapter, id, md_text):
    html_portion = markdown.markdown(md_text)

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
            h1, h2 {{
                color: #104061; /* Vibrant blue for headings */
                font-size: 30px;
                border-bottom: 1px solid #6f8695;
                border-top: 3px solid #6f8695;
                padding: 10px 0;
            }}
            h2 {{
                font-size: 20px;
            }}
            p {{
                font-size: 16px;
                line-height: 1.6;
            }}
            a {{
                color: #6699ff; /* Lighter blue for links */
                text-decoration: none;
            }}
            a:hover {{
                text-decoration: underline;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
            }}
            th, td {{
                padding: 8px;
                text-align: left;
                border-bottom: 1px solid #ddd;
            }}
            th {{
                background-color: #cce6ff; /* Light blue for table headers */
            }}
            code{{
                display: block;
                padding: 20px;
                border-radius: 5px;
                background-color: #eeeae6;
            }}
            img{{
                display: block;
                height: 250px;
                margin: 0 auto;
            }}
        </style>
    </head>
    <body>
        {html_portion}
    </body>
    </html>
    """

    os.makedirs(f'./data/{chapter}', exist_ok=True)
    with open(f'./data/{chapter}/{id}.html', 'w') as file:
        file.write(styled_html)

    return styled_html

def save_title(i, chapter):
    html_portion = markdown.markdown(f'## CH{i}. \n# {chapter}')

    styled_html = f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <title>Document</title>
        <style>
            body {{
                font-family: 'Arial', sans-serif;
                margin: 0;
                background-color: #ffffff; /* White background */
                color: #333366; /* Dark blue text */
                height: 85vh;
                display: flex;
                justify-content: center;
                align-items: center;
                flex-direction: column;
            }}
            h1, h2 {{
                color: #104061; 
                font-size: 60px;
                padding: 10px 0;
                margin: 10px;
            }}
            h2 {{
                font-size: 20px;
            }}
        </style>
    </head>
    <body>
        {html_portion}
    </body>
    </html>
    """
    os.makedirs(f'./data/{chapter}', exist_ok=True)
    with open(f'./data/{chapter}/title.html', 'w') as file:
        file.write(styled_html)

    return styled_html

def crawl():
    for j, chapter in enumerate(problem_list.keys()):
            save_title(j+1, chapter)
            for i, id in enumerate(problem_list[chapter]):
                html = getBOJHTML(id)
                md = save_page_md(id, i+1, html)
                save_page_html(chapter, id, md)

if __name__ == "__main__":
    crawl()