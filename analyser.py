from flask import Flask, request, render_template, send_file
import requests
from bs4 import BeautifulSoup
import nltk
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
from io import StringIO
import json
import concurrent.futures
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from datetime import datetime
from collections import Counter

app = Flask(__name__)

nltk.download('stopwords')
nltk.download('punkt')
stop_words = set(stopwords.words('english'))

# --- Selenium Headless Chrome Utility ---
def fetch_page_data(url):
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1280,1024")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    driver.get(url)

    # Take desktop screenshot
    desktop_screenshot = 'static/desktop_preview.png'
    driver.save_screenshot(desktop_screenshot)

    # Take mobile screenshot
    driver.set_window_size(360, 640)
    mobile_screenshot = 'static/mobile_preview.png'
    driver.save_screenshot(mobile_screenshot)

    # Get load time
    timing = driver.execute_script("return window.performance.timing")
    load_time = (timing['loadEventEnd'] - timing['navigationStart']) / 1000

    html = driver.page_source
    driver.quit()
    return html, load_time, mobile_screenshot, desktop_screenshot

# --- Keyword Extraction Optimized ---
def extract_top_keywords(text, top_n=10):
    words = word_tokenize(text.lower())
    words_filtered = [w for w in words if w.isalpha() and w not in stop_words]
    return Counter(words_filtered).most_common(top_n)

# --- Check if Page is Mobile Friendly ---
def check_mobile_friendly(soup):
    if soup.find('meta', attrs={'name': 'viewport'}):
        return "Viewport tag exists. The page is likely mobile-friendly."
    return "Viewport tag is missing! Consider adding it."

# --- Schema Detection ---
def detect_schema(soup):
    types = []
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string)
            if '@type' in data:
                types.append(data['@type'])
        except:
            continue
    return types

# --- Accessibility Checks ---
def check_accessibility(soup):
    issues = []
    for img in soup.find_all('img'):
        if not img.get('alt'):
            issues.append(f"Image with src '{img.get('src')}' is missing alt text.")
    return issues

# --- Parallel Broken Link Checker ---
def check_broken_links(soup, base_url):
    links = [a['href'] for a in soup.find_all('a', href=True)]

    def is_broken(href):
        try:
            if not href.startswith(('http://', 'https://')):
                href = base_url.rstrip('/') + '/' + href.lstrip('/')
            r = requests.head(href, timeout=3)
            if r.status_code >= 400:
                return href
        except:
            return href
        return None

    broken = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        for result in executor.map(is_broken, links):
            if result:
                broken.append(result)
    return broken

# --- Social Media Meta Checks ---
def check_social_meta(soup):
    tags = {
        'og:title': 'Open Graph Title',
        'og:description': 'Open Graph Description',
        'twitter:card': 'Twitter Card'
    }
    missing = []
    for tag, desc in tags.items():
        if not soup.find('meta', attrs={'property': tag}) and not soup.find('meta', attrs={'name': tag}):
            missing.append(f"{desc} ({tag}) is missing.")
    return missing

# --- Main SEO Analysis Function ---
def analyze_seo(url):
    html, load_time, mobile_ss, desktop_ss = fetch_page_data(url)
    soup = BeautifulSoup(html, 'html.parser')

    good, bad, recommendations = [], [], []
    score = 100
    image_alts, title_keywords = [], []

    # Title
    title_tag = soup.find('title')
    seo_title = title_tag.get_text().strip() if title_tag else None
    if seo_title:
        good.append("Title Exists! Great!")
    else:
        bad.append("Title does not exist!")
        recommendations.append("Add a title.")
        score -= 10

    # Meta Description
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    seo_description = meta_desc.get('content').strip() if meta_desc and meta_desc.get('content') else None
    if seo_description and len(seo_description) > 50:
        good.append("Description Exists! Great!")
    else:
        bad.append("Description is missing or too short!")
        recommendations.append("Add a meta description.")
        score -= 10

    # Headings
    headings = [h for h in soup.find_all(['h1','h2','h3','h4','h5','h6'])]
    for h in headings:
        good.append(f"{h.name}: {h.text.strip()}")
    h1_tags = soup.find_all('h1')
    if not h1_tags:
        bad.append("No H1 found!")
        recommendations.append("Add an H1 tag.")
        score -= 10
    elif len(h1_tags) > 1:
        bad.append(f"Multiple H1 tags found: {len(h1_tags)}")
        recommendations.append("Use only one H1.")
        score -= 5
    else:
        good.append(f"One H1 tag found: {h1_tags[0].text.strip()}")

    # Image ALTs
    for img in soup.find_all('img'):
        if not img.get('alt'):
            bad.append(f"Image missing alt: {img.get('src')}")
            recommendations.append(f"Add alt to {img.get('src')}")
            score -= 5
        elif img.get('alt').strip():
            image_alts.append(img.get('alt').strip())

    # Keyword Extraction
    body_text = soup.get_text()
    keywords = extract_top_keywords(body_text)
    title_words = word_tokenize(seo_title.lower()) if seo_title else []
    title_keywords = [w for w in title_words if w.isalpha() and w not in stop_words]

    # Keyword Density (example only)
    total_words = len(body_text.split())
    keyword_density = {kw: (freq/total_words)*100 for kw, freq in keywords} if total_words > 0 else {}

    # Links ratio
    internal, external = 0, 0
    for a in soup.find_all('a', href=True):
        if a['href'].startswith(url):
            internal += 1
        else:
            external += 1
    links_ratio = {'internal': internal, 'external': external}

    return (
        good, bad, keywords, score, seo_title, seo_description,
        image_alts, links_ratio, title_keywords, recommendations,
        keyword_density, check_mobile_friendly(soup), detect_schema(soup),
        check_accessibility(soup), load_time,
        check_broken_links(soup, url), check_social_meta(soup),
        mobile_ss, desktop_ss
    )

# --- Report Generator ---
def generate_report(*args):
    (
        good, bad, keywords, score, seo_title, seo_description,
        image_alts, links_ratio, title_keywords, recommendations,
        keyword_density, mobile_friendly, schema_types,
        accessibility_issues, load_time,
        broken_links, social_media_issues
    ) = args

    report = StringIO()
    report.write(f"SEO Report\nScore: {score}\n\n")
    report.write(f"Title: {seo_title}\nDescription: {seo_description}\n\n")
    report.write("Top Keywords:\n" + "\n".join([f"{k}: {v}" for k,v in keywords]) + "\n\n")
    report.write("Keyword Density:\n" + "\n".join([f"{k}: {v:.2f}%" for k,v in keyword_density.items()]) + "\n\n")
    report.write(f"Mobile-Friendliness: {mobile_friendly}\n\n")
    report.write("Schema Types:\n" + "\n".join(schema_types) + "\n\n")
    report.write("Accessibility Issues:\n" + "\n".join(accessibility_issues) + "\n\n")
    report.write(f"Page Load Time: {load_time:.2f} seconds\n\n")
    report.write("Broken Links:\n" + "\n".join(broken_links) + "\n\n")
    report.write("Social Media Issues:\n" + "\n".join(social_media_issues) + "\n\n")
    report.write("Good:\n" + "\n".join(good) + "\n\n")
    report.write("Bad:\n" + "\n".join(bad) + "\n\n")
    report.write("Recommendations:\n" + "\n".join(recommendations) + "\n\n")
    report.write("Image ALTs:\n" + "\n".join(image_alts) + "\n\n")
    report.write(f"Internal Links: {links_ratio['internal']}\nExternal Links: {links_ratio['external']}\n")
    return report.getvalue()

# --- Flask Routes ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    url = request.form.get('url')
    if not url:
        return "URL is required", 400

    results = analyze_seo(url)
    report_text = generate_report(*results[:-2])

    with open('static/seo_report.txt', 'w') as f:
        f.write(report_text)

    return render_template('results.html', **{
        'good': results[0], 'bad': results[1], 'keywords': results[2],
        'score': results[3], 'seo_title': results[4], 'seo_description': results[5],
        'image_alt_attributes': results[6], 'links_ratio': results[7],
        'title_keywords': results[8], 'recommendations': results[9],
        'keyword_density': results[10], 'mobile_friendly': results[11],
        'schema_types': results[12], 'accessibility_issues': results[13],
        'page_load_time': results[14], 'broken_links': results[15],
        'social_media_issues': results[16],
        'mobile_screenshot_path': results[17], 'desktop_screenshot_path': results[18],
    })

@app.route('/download_report')
def download_report():
    return send_file('static/seo_report.txt', as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)