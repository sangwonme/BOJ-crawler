import html2text
import requests
import os
from bs4 import BeautifulSoup
import markdown
import pdfkit

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
    
def save_page_md(id, html):
    # Parse the HTML content
    soup = BeautifulSoup(html, 'html.parser')

    # title
    title = soup.find('span', id='problem_title').text

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
    markdown_content = f"# {id}. {title}\n"
    for element in [problem_description, input_description, output_description]:
        if element:
            markdown_content += h.handle(str(element))

    for element in sample_io:
        if element:
            markdown_content += h.handle(str(element).replace('복사', ''))

    # Save to a Markdown file
    with open('output.md', 'w') as file:
        file.write(markdown_content)

    tmp = markdown_to_html(markdown_content)

    import pdb ; pdb.set_trace()
    html_to_pdf(tmp, 'output.pdf')


    print("Content saved to 'output.md'")

# Convert Markdown to HTML
def markdown_to_html(md_text):
    html = markdown.markdown(md_text)
    return html

# Convert HTML to PDF
def html_to_pdf(html, output_filename):
    # Set the path to the wkhtmltopdf executable
    path_wkhtmltopdf = '/usr/local/bin/wkhtmltopdf'  # Update this path
    config = pdfkit.configuration(wkhtmltopdf=path_wkhtmltopdf)

    # Use this config when converting
    pdfkit.from_string(html, output_filename, configuration=config)



if __name__ == "__main__":
    id = 2468
    html = getBOJHTML(id)
    save_page_md(id, html)

