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
import base64

class BOJProblemFetcher:
    BASE_URL = 'https://www.acmicpc.net/problem/'
    SOLVED_AC_API = 'https://solved.ac/api/v3/problem/show'

    def __init__(self, problem_id, chapter=1, output_dir='./data', subdir=None, filename=None, embed_images=False):
        """
        Initialize the BOJProblemFetcher.

        :param problem_id: ID of the BOJ problem to fetch.
        :param chapter: Chapter number for organizing output.
        :param output_dir: Base directory where outputs are saved.
        :param subdir: Additional subdirectory path relative to output_dir.
        :param filename: Custom filename for the output HTML file.
        :param embed_images: If True, embed images as Base64 in HTML.
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
            ),
            'Referer': 'https://www.acmicpc.net'  # Added Referer header
        }
        self.embed_images = embed_images  # New parameter to control image embedding

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

    def download_and_replace_images(self, html_content):
        """
        Download all images in the HTML content and replace their src with local paths.

        :param html_content: HTML content as a string.
        :return: Modified HTML content with updated image sources.
        """
        soup = BeautifulSoup(html_content, 'html.parser')

        # Create images directory
        images_dir = self.output_dir / self.subdir / 'images'
        images_dir.mkdir(parents=True, exist_ok=True)

        for img in soup.find_all('img'):
            img_url = img.get('src')
            if not img_url:
                continue

            # Handle relative URLs
            if img_url.startswith('/'):
                img_url = f'https://www.acmicpc.net{img_url}'

            try:
                img_response = requests.get(img_url, headers=self.headers)
                img_response.raise_for_status()

                # Determine image filename
                img_filename = os.path.basename(img_url)
                local_img_path = images_dir / img_filename

                # Save image locally
                with open(local_img_path, 'wb') as f:
                    f.write(img_response.content)
                print(f'Downloaded image: {img_url} to {local_img_path}')

                # Replace src with relative path
                img['src'] = f'images/{img_filename}'

            except requests.HTTPError as http_err:
                print(f'Failed to download image {img_url}: {http_err}')
                # Optionally, replace with placeholder or remove the img tag
                img.decompose()  # Remove the img tag
                continue

            except Exception as e:
                print(f'An error occurred while downloading image {img_url}: {e}')
                img.decompose()  # Remove the img tag
                continue

        return str(soup)

    def embed_images_as_base64(self, html_content):
        """
        Embed all images in the HTML content as Base64.

        :param html_content: HTML content as a string.
        :return: Modified HTML content with embedded images.
        """
        soup = BeautifulSoup(html_content, 'html.parser')

        for img in soup.find_all('img'):
            img_url = img.get('src')
            if not img_url:
                continue

            # Handle relative URLs
            if img_url.startswith('/'):
                img_url = f'https://www.acmicpc.net{img_url}'

            try:
                img_response = requests.get(img_url, headers=self.headers)
                img_response.raise_for_status()

                # Get image MIME type
                content_type = img_response.headers.get('Content-Type')
                if not content_type:
                    print(f'Could not determine content type for image: {img_url}')
                    continue

                # Encode image in Base64
                encoded_string = base64.b64encode(img_response.content).decode('utf-8')
                data_uri = f"data:{content_type};base64,{encoded_string}"

                # Replace src with data URI
                img['src'] = data_uri

                print(f'Embedded image: {img_url} as Base64')

            except requests.HTTPError as http_err:
                print(f'Failed to embed image {img_url}: {http_err}')
                # Optionally, replace with placeholder or remove the img tag
                img.decompose()  # Remove the img tag
                continue

            except Exception as e:
                print(f'An error occurred while embedding image {img_url}: {e}')
                img.decompose()  # Remove the img tag
                continue

        return str(soup)

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

        # Process images in each section
        if description:
            description_html = str(description)
            if self.embed_images:
                description_html = self.embed_images_as_base64(description_html)
            else:
                description_html = self.download_and_replace_images(description_html)
            description = description_html

        if input_section:
            input_html = str(input_section)
            if self.embed_images:
                input_html = self.embed_images_as_base64(input_html)
            else:
                input_html = self.download_and_replace_images(input_html)
            input_section = input_html

        if output_section:
            output_html = str(output_section)
            if self.embed_images:
                output_html = self.embed_images_as_base64(output_html)
            else:
                output_html = self.download_and_replace_images(output_html)
            output_section = output_html

        # Process images in sample sections
        processed_samples = []
        for inp, outp in sample_io:
            if self.embed_images:
                inp = self.embed_images_as_base64(inp)
                outp = self.embed_images_as_base64(outp)
            else:
                inp = self.download_and_replace_images(inp)
                outp = self.download_and_replace_images(outp)
            processed_samples.append((inp, outp))

        return {
            'title': title,
            'description': description if description else '',
            'input': input_section if input_section else '',
            'output': output_section if output_section else '',
            'samples': processed_samples
        }

    def convert_to_markdown(self, parsed_data, level):
        """Convert the parsed HTML data to Markdown format."""
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = False
        h.ignore_emphasis = False

        # md_content = f"# {self.problem_id}. {parsed_data['title']}\n"
        md_content = f"# {self.problem_id}. {parsed_data['title']}\n"

        for section, heading in [('description', 'Description'),
                                 ('input', 'Input'),
                                 ('output', 'Output')]:
            if parsed_data[section]:
                md_content += h.handle(parsed_data[section]) + "\n"

        if parsed_data['samples']:
            md_content += "## 예제 입출력 \n"
            for idx, (inp, outp) in enumerate(parsed_data['samples'], 1):
                md_content += f"### 예제 {idx}\n\n"
                md_content += f"**Input:**\n\n```\n{inp}\n```\n\n"
                md_content += f"**Output:**\n\n```\n{outp}\n```\n\n"
        md_content = re.sub(r'예제\s+(입력|출력)\s*\d+\s*복사', '', md_content)
        
        # preprocess
        md_content = md_content.replace('$', '')
        md_content = md_content.replace('\\times', ' X ')
        md_content = md_content.replace('^\circ', '°')
        md_content = md_content.replace('\\le', '≤')
        
        return md_content

    def convert_markdown_to_html(self, md_text):
        """Convert Markdown text to styled HTML."""
        html_content = markdown.markdown(md_text, extensions=['fenced_code', 'tables'])

        # Determine the base path for relative URLs
        base_path = self.output_dir / self.subdir
        base_uri = base_path.resolve().as_uri() + '/'

        styled_html = f"""
        <!DOCTYPE html>
        <html lang="ko">
        <head>
            <meta charset="UTF-8">
            <base href="{base_uri}">
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
            # Define options for pdfkit
            options = {
                'enable-local-file-access': None,  # Allows accessing local files
                'quiet': '',  # Suppress wkhtmltopdf output
            }

            # Set the base URL to the directory containing the HTML file
            base_url = str(full_output_path.resolve())

            # Convert HTML to PDF with options and base_url
            pdfkit.from_file(
                str(html_file_path),
                str(pdf_file_path),
                options=options,
                configuration=pdfkit.configuration(),  # Ensure wkhtmltopdf is properly configured
                # base_url=base_url  # Critical for resolving relative paths
            )
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
        # self.convert_html_to_pdf(html_content)

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
    # Example: Fetch and save problems from 'easy_set.csv'


    problem_set = pd.read_csv('easy_set.csv')

    for i in range(len(problem_set)):
        problem_id = int(problem_set.loc[i, 'ID'])
        chapter = problem_set.loc[i, 'algorithm_name']
        print(f'Processing Problem ID: {problem_id}')

        # Initialize the fetcher with default output settings
        # Set embed_images=True to embed images as Base64 in HTML and PDF
        # Set embed_images=False to download images and reference them locally
        fetcher = BOJProblemFetcher(
            problem_id=problem_id,
            chapter=chapter,
            embed_images=False  # Change to True if you prefer embedding images
        )

        # Optionally, set a custom output directory and subdirectory
        fetcher.set_output_directory('./problems')
        fetcher.set_subdirectory(chapter)
        fetcher.set_filename(f'{problem_id}.html')  # Optional: set a custom filename

        # Execute the fetching and saving process
        fetcher.process()
