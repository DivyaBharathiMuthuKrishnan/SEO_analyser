from flask import Flask, render_template, request
import requests
from bs4 import BeautifulSoup
import time

app = Flask(__name__)

# Home page
@app.route('/')
def index():
    return render_template('index.html')

# Analyze route
@app.route('/analyze', methods=['POST'])
def analyze():
    url = request.form['url']
    if not url.startswith('http'):
        url = 'http://' + url

    try:
        html, load_time = fetch_page_data(url)
        results = analyze_seo(html, load_time, url)
        return render_template('results.html', results=results, url=url)
    except Exception as e:
        return f"Error: {str(e)}"

# Fetch page HTML using requests
def fetch_page_data(url):
    start_time = time.time()
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    html = response.text
    load_time = round(time.time() - start_time, 2)
    return html, load_time

# Perform SEO analysis
def analyze_seo(html, load_time, url):
    soup = BeautifulSoup(html, 'html.parser')
    results = {}

    # Basic info
    results['load_time'] = load_time
    results['title'] = soup.title.string.strip() if soup.title else 'No title found'
    
    # Meta description
    meta_desc_tag = soup.find('meta', attrs={'name': 'description'})
    results['meta_description'] = meta_desc_tag['content'].strip() if meta_desc_tag and 'content' in meta_desc_tag.attrs else 'No meta description found'

    # Headings
    headings = {}
    for i in range(1, 7):
        tags = soup.find_all(f'h{i}')
        headings[f'h{i}'] = [tag.get_text(strip=True) for tag in tags]
    results['headings'] = headings

    # Number of links
    links = soup.find_all('a')
    results['total_links'] = len(links)

    # Example: All link URLs
    results['links'] = [link.get('href') for link in links if link.get('href')]

    # Images count
    images = soup.find_all('img')
    results['total_images'] = len(images)

    # Example: All image sources
    results['images'] = [img.get('src') for img in images if img.get('src')]

    return results

# For local development
if __name__ == '__main__':
    app.run(debug=True)
