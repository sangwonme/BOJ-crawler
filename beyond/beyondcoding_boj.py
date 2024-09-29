import os
import json
import requests
import markdown
import html2text
from bs4 import BeautifulSoup
from pathlib import Path
import re
import pandas as pd
import pdfkit
import argparse


class BOJProblemFetcher:
    BASE_URL = 'https://www.acmicpc.net/problem/'
    SOLVED_AC_API = 'https://solved.ac/api/v3/problem/show'

    def __init__(self, problem_id, chapter=1, output_dir='./data', subdir=None, filename=None):
        """
        Initialize the BOJProblemFetcher.

        :param problem_id: ID of the BOJ problem to fetch.
        :param chapter: Chapter number for organizing output.
        :param output_dir: Base directory where outputs are saved.
        :param subdir: Additional subdirectory path relative to output_dir.
        :param filename: Custom filename for the output HTML file.
        """
        self.problem_id = problem_id
        self.chapter = chapter
        self.output_dir = Path(output_dir)
        self.subdir = Path(subdir) if subdir else Path(f'chapter_{chapter}')
        self.filename = filename if filename else f'{self.problem_id}.html'
        self.pdf_filename = self.filename.replace('.html', '.pdf') 
        self.headers = {
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/91.0.4472.77 Safari/537.36'
            )
        }

    def set_output_directory(self, output_dir):
        """
        Set a new base output directory.

        :param output_dir: New base directory path.
        """
        self.output_dir = Path(output_dir)

    def set_subdirectory(self, subdir):
        """
        Set a new subdirectory within the base output directory.

        :param subdir: New subdirectory path relative to output_dir.
        """
        self.subdir = Path(subdir)

    def set_filename(self, filename):
        """
        Set a new filename for the output HTML file.

        :param filename: New filename (e.g., 'problem_1000.html').
        """
        self.filename = filename

    def fetch_html(self):
        """Fetch the HTML content of the BOJ problem page."""
        url = f"{self.BASE_URL}{self.problem_id}"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()  # Raise an exception for HTTP errors
        return response.text

    def fetch_problem_level(self):
        """Fetch the problem's difficulty level from solved.ac API."""
        params = {'problemId': self.problem_id}
        response = requests.get(self.SOLVED_AC_API, params=params)
        response.raise_for_status()
        data = response.json()
        return data.get('level', 1)  # Default to level 1 if not found

    def parse_html(self, html):
        """Parse the HTML content and extract relevant sections."""
        soup = BeautifulSoup(html, 'html.parser')

        # Extract title
        title_tag = soup.find('span', id='problem_title')
        title = title_tag.get_text(strip=True) if title_tag else f"Problem {self.problem_id}"

        # Extract problem description, input, and output sections
        description = soup.find('div', id='problem_description')
        input_section = soup.find('section', id='input')
        output_section = soup.find('section', id='output')

        # Extract sample inputs and outputs
        sample_io = []
        index = 1
        while True:
            sample_input = soup.find('section', id=f'sampleinput{index}')
            sample_output = soup.find('section', id=f'sampleoutput{index}')
            if not sample_input or not sample_output:
                break
            sample_io.append((sample_input.get_text(strip=True), sample_output.get_text(strip=True)))
            index += 1

        return {
            'title': title,
            'description': str(description) if description else '',
            'input': str(input_section) if input_section else '',
            'output': str(output_section) if output_section else '',
            'samples': sample_io
        }

    def convert_to_markdown(self, parsed_data, level):
        """Convert the parsed HTML data to Markdown format."""
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = False
        h.ignore_emphasis = False

        # Calculate stars based on level
        # star_count = min((level - 1) // 5 + 1, 3)  # Cap at 3 stars
        # stars = '★' * star_count + '☆' * (3 - star_count)

        # md_content = f"# {parsed_data['title']} {stars}\n\n"
        md_content = f"# {self.problem_id}. {parsed_data['title']}\n"

        for section, heading in [('description', 'Description'),
                                 ('input', 'Input'),
                                 ('output', 'Output')]:
            if parsed_data[section]:
                # md_content += f"## {heading}\n\n"
                md_content += h.handle(parsed_data[section]) + "\n"

        if parsed_data['samples']:
            md_content += "## 예제 입출력 \n"
            for idx, (inp, outp) in enumerate(parsed_data['samples'], 1):
                md_content += f"### 예제 {idx}\n\n"
                md_content += f"**Input:**\n\n```\n{inp}\n```\n\n"
                md_content += f"**Output:**\n\n```\n{outp}\n```\n\n"
        md_content = re.sub(r'예제\s+(입력|출력)\s*\d+\s*복사', '', md_content)
        return md_content

    def convert_markdown_to_html(self, md_text):
        """Convert Markdown text to styled HTML."""
        html_content = markdown.markdown(md_text, extensions=['fenced_code', 'tables'])

        styled_html = f"""
        <!DOCTYPE html>
        <html lang="ko">
        <head>
            <meta charset="UTF-8">
            <title>{self.problem_id} - BOJ Problem</title>
            <style>
                body {{
                    font-family: 'Arial', sans-serif;
                    margin: 40px;
                    background-color: #ffffff;
                    color: #333366;
                }}
                h1, h2, h3 {{
                    color: #104061;
                    border-bottom: 1px solid #6f8695;
                    padding-bottom: 5px;
                }}
                h1 {{
                    font-size: 2em;
                }}
                h2 {{
                    font-size: 1.5em;
                }}
                h3 {{
                    font-size: 1.2em;
                }}
                p, pre, code, table {{
                    font-size: 1em;
                    line-height: 1.6;
                }}
                a {{
                    color: #6699ff;
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
                    background-color: #cce6ff;
                }}
                pre {{
                    background-color: #eeeae6;
                    padding: 10px;
                    border-radius: 5px;
                    overflow-x: auto;
                }}
                code {{
                    padding: 2px 4px;
                    padding-left: 0;
                    border-radius: 3px;
                }}
                img {{
                    display: block;
                    max-width: 100%;
                    height: auto;
                    margin: 20px auto;
                }}
            </style>
        </head>
        <body>
            {html_content}
        </body>
        </html>
        """
        return styled_html

    def save_html(self, html_content):
        """Save the styled HTML to a file."""
        # Define the full output path
        full_output_path = self.output_dir / self.subdir
        full_output_path.mkdir(parents=True, exist_ok=True)  # Create directories if they don't exist

        file_path = full_output_path / self.filename

        with open(file_path, 'w', encoding='utf-8') as file:
            file.write(html_content)
        print(f'HTML saved to: {file_path.resolve()}')


    def convert_html_to_pdf(self, html_content):
        """Convert HTML content to PDF."""
        # Define the full output path
        full_output_path = self.output_dir / self.subdir
        full_output_path.mkdir(parents=True, exist_ok=True)  # Create directories if they don't exist

        html_file_path = full_output_path / self.filename
        pdf_file_path = full_output_path / self.pdf_filename

        # Save the HTML content to a temporary file
        with open(html_file_path, 'w', encoding='utf-8') as file:
            file.write(html_content)
        print(f'HTML saved to: {html_file_path.resolve()}')

        try:
            # Convert HTML to PDF
            pdfkit.from_file(str(html_file_path), str(pdf_file_path))
            print(f'PDF saved to: {pdf_file_path.resolve()}')
        except Exception as e:
            print(f'Failed to convert HTML to PDF: {e}')

    def save_html_and_pdf(self, html_content):
        """Save the styled HTML and convert it to PDF."""
        # Define the full output path
        full_output_path = self.output_dir / self.subdir
        full_output_path.mkdir(parents=True, exist_ok=True)  # Create directories if they don't exist

        html_file_path = full_output_path / self.filename
        pdf_file_path = full_output_path / self.pdf_filename

        # Save HTML
        with open(html_file_path, 'w', encoding='utf-8') as file:
            file.write(html_content)
        print(f'HTML saved to: {html_file_path.resolve()}')

        # Convert HTML to PDF
        try:
            pdfkit.from_file(str(html_file_path), str(pdf_file_path))
            print(f'PDF saved to: {pdf_file_path.resolve()}')
        except Exception as e:
            print(f'Failed to convert HTML to PDF: {e}')

    def process(self):
        """Execute the full processing pipeline."""
        try:
            html = self.fetch_html()
            level = self.fetch_problem_level()
            parsed_data = self.parse_html(html)
            md_text = self.convert_to_markdown(parsed_data, level)
            styled_html = self.convert_markdown_to_html(md_text)
            self.save_html_and_pdf(styled_html)  # Save both HTML and PDF
        except requests.HTTPError as http_err:
            print(f'HTTP error occurred: {http_err}')
        except Exception as err:
            print(f'An error occurred: {err}')


# Example Usage
if __name__ == "__main__":
    # Example: Fetch and save problem #1000

    problem_set = pd.read_csv('./easy_set.csv')

    for i in range(len(problem_set)):
        problem_id = int(problem_set.loc[i, 'problem_id'])
        chapter = problem_set.loc[i, 'category']
        print(problem_id)

        # Initialize the fetcher with default output settings
        fetcher = BOJProblemFetcher(problem_id=problem_id, chapter=chapter)

        # Optionally, set a custom output directory and subdirectory
        fetcher.set_output_directory('./problems')
        fetcher.set_subdirectory('simulation')
        fetcher.set_filename(f'{problem_id}.html')  # Optional: set a custom filename

        # Execute the fetching and saving process
        fetcher.process()
