# Resturant-Data-Scraper
Scrapes relevant data from a website using 2-Layers: Scrape all the data using BS4 and Selenium. Filter data using LLMs

## Setup Instructions

Follow the steps below to get started:

### 1. Clone the Repository

```bash
git clone https://github.com/your-username/website-analyzer.git
cd website-analyzer
```

### 2. Create a `.env` File

Create a `.env` file in the root directory of the project and add your GROQ API key:

```env
GROQ_API_KEY=your_groq_api_key_here
```

> ⚠️ **Important:** Do not share your API key publicly.

### 3. Set the Target Website URL

Open the `main.py` file and locate the following line:

```python
website_url = "https://www.yangskitchenla.com/"
```

Change the URL to the website you want to analyze:

```python
website_url = "https://www.example.com/"
```

### 4. Run the Script


Run the script:

```bash
python main.py
```

## Requirements

- Python 3.8+
- GROQ API Key
- Required packages (listed in `requirements.txt`)

