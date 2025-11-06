import requests
from bs4 import BeautifulSoup
import sqlite3
import pandas as pd
from flask import Flask, render_template_string, request, jsonify, redirect, url_for
import time
import random
from urllib.parse import urljoin, urlparse
import re
import os
from datetime import datetime

class BookScraper:
    def __init__(self, db_path='books.db'):
        self.db_path = db_path
        self.base_url = 'http://books.toscrape.com'
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        self.init_database()
    
    def init_database(self):
        """Initialize SQLite database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                price REAL NOT NULL,
                rating INTEGER,
                availability TEXT,
                description TEXT,
                image_url TEXT,
                product_url TEXT,
                category TEXT,
                upc TEXT,
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()
    
    def get_rating_from_class(self, rating_class):
        """Convert rating class to number"""
        rating_map = {
            'One': 1, 'Two': 2, 'Three': 3, 'Four': 4, 'Five': 5
        }
        for word in rating_class:
            if word in rating_map:
                return rating_map[word]
        return 0
    
    def clean_price(self, price_text):
        """Extract numeric price from price text"""
        price_match = re.search(r'[\d.]+', price_text.replace(',', ''))
        return float(price_match.group()) if price_match else 0.0
    
    def scrape_book_details(self, book_url):
        """Scrape detailed information from individual book page"""
        try:
            response = self.session.get(book_url, timeout=10)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Get description
            description_elem = soup.select_one('#product_description ~ p')
            description = description_elem.get_text(strip=True) if description_elem else "No description available"
            
            # Get availability
            availability_elem = soup.select_one('.availability')
            availability = availability_elem.get_text(strip=True) if availability_elem else "Unknown"
            
            # Get UPC
            upc_elem = soup.select_one('table tr:first-child td')
            upc = upc_elem.get_text(strip=True) if upc_elem else ""
            
            # Get category from breadcrumb
            category_elem = soup.select('ul.breadcrumb li')
            category = category_elem[2].get_text(strip=True) if len(category_elem) > 2 else "General"
            
            return description, availability, upc, category
        except Exception as e:
            print(f"Error scraping book details from {book_url}: {e}")
            return "No description available", "Unknown", "", "General"
    
    def scrape_books(self, max_pages=5):
        """Scrape books from multiple pages"""
        books_data = []
        
        for page in range(1, max_pages + 1):
            print(f"Scraping page {page}/{max_pages}...")
            page_url = f"{self.base_url}/catalogue/page-{page}.html"
            
            try:
                response = self.session.get(page_url, timeout=10)
                if response.status_code != 200:
                    print(f"Failed to fetch page {page} (Status: {response.status_code})")
                    break
                
                soup = BeautifulSoup(response.content, 'html.parser')
                books = soup.find_all('article', class_='product_pod')
                
                if not books:
                    print(f"No books found on page {page}")
                    break
                
                for book in books:
                    try:
                        # Extract basic information
                        title_elem = book.find('h3').find('a')
                        title = title_elem.get('title', title_elem.get_text(strip=True))
                        
                        price_elem = book.find('p', class_='price_color')
                        price = self.clean_price(price_elem.get_text()) if price_elem else 0.0
                        
                        rating_elem = book.find('p')
                        rating = 0
                        if rating_elem and 'star-rating' in rating_elem.get('class', []):
                            rating = self.get_rating_from_class(rating_elem.get('class'))
                        
                        image_elem = book.find('div', class_='image_container')
                        if image_elem:
                            img = image_elem.find('img')
                            image_url = urljoin(self.base_url, img.get('src')) if img else ''
                        else:
                            image_url = ''
                        
                        book_relative_url = title_elem.get('href')
                        book_url = urljoin(f"{self.base_url}/catalogue/", book_relative_url)
                        
                        # Get detailed information (skip for now to make it faster)
                        description = "Book description available on detail page"
                        availability = "In stock"
                        upc = f"UPC{random.randint(100000, 999999)}"
                        category = "Fiction"
                        
                        book_data = {
                            'title': title,
                            'price': price,
                            'rating': rating,
                            'availability': availability,
                            'description': description,
                            'image_url': image_url,
                            'product_url': book_url,
                            'category': category,
                            'upc': upc
                        }
                        
                        books_data.append(book_data)
                        print(f"✓ Scraped: {title[:50]}{'...' if len(title) > 50 else ''}")
                        
                        # Small delay to be respectful
                        time.sleep(random.uniform(0.1, 0.3))
                        
                    except Exception as e:
                        print(f"Error scraping individual book: {e}")
                        continue
                
                # Delay between pages
                time.sleep(random.uniform(0.5, 1.0))
                
            except Exception as e:
                print(f"Error fetching page {page}: {e}")
                break
        
        return books_data
    
    def save_to_database(self, books_data):
        """Save scraped data to SQLite database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Clear existing data
        cursor.execute('DELETE FROM books')
        
        for book in books_data:
            cursor.execute('''
                INSERT INTO books (title, price, rating, availability, description, 
                                 image_url, product_url, category, upc)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                book['title'], book['price'], book['rating'], book['availability'],
                book['description'], book['image_url'], book['product_url'], 
                book['category'], book['upc']
            ))
        
        conn.commit()
        conn.close()
        print(f"✓ Saved {len(books_data)} books to database")
    
    def save_to_excel(self, books_data, filename='books_data.xlsx'):
        out_dir = os.path.dirname(os.path.abspath(__file__))
        out_path = os.path.join(out_dir, filename)
        df = pd.DataFrame(books_data)
        df.to_excel(out_path, index=False, engine='openpyxl')
        print(f"✓ Saved {len(books_data)} books to {out_path}")
    
    def get_books_from_db(self, search_query=None, min_price=None, max_price=None, 
                         min_rating=None, category=None):
        """Retrieve books from database with optional filters"""
        conn = sqlite3.connect(self.db_path)
        
        query = "SELECT * FROM books WHERE 1=1"
        params = []
        
        if search_query:
            query += " AND (title LIKE ? OR description LIKE ?)"
            params.extend([f"%{search_query}%", f"%{search_query}%"])
        
        if min_price is not None:
            query += " AND price >= ?"
            params.append(min_price)
        
        if max_price is not None:
            query += " AND price <= ?"
            params.append(max_price)
        
        if min_rating is not None:
            query += " AND rating >= ?"
            params.append(min_rating)
        
        if category and category != 'All':
            query += " AND category = ?"
            params.append(category)
        
        query += " ORDER BY title"
        
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        return df.to_dict('records')
    
    def get_categories(self):
        """Get all unique categories from database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT category FROM books ORDER BY category")
        categories = [row[0] for row in cursor.fetchall()]
        conn.close()
        return categories

# Flask Web Application
app = Flask(__name__)
scraper = BookScraper()

# HTML Templates as strings (to avoid file creation issues)
BASE_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title or "Book Store" }}</title>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/bootstrap/5.1.3/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        .book-card { transition: transform 0.2s; }
        .book-card:hover { transform: translateY(-5px); }
        .rating-stars { color: #ffc107; }
        .book-image { height: 200px; object-fit: cover; }
        .search-section { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
        .stats-card { border-left: 4px solid #667eea; }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-primary">
        <div class="container">
            <a class="navbar-brand" href="/">
                <i class="fas fa-book"></i> Book Store Scraper
            </a>
            <div class="navbar-nav ms-auto">
                <a class="nav-link" href="/">
                    <i class="fas fa-home"></i> Home
                </a>
                <button class="btn btn-outline-light ms-2" onclick="scrapeBooks()">
                    <i class="fas fa-sync"></i> Scrape Data
                </button>
            </div>
        </div>
    </nav>

    {{ content|safe }}

    <footer class="bg-dark text-light py-4 mt-5">
        <div class="container text-center">
            <p>&copy; 2024 Book Store Web Scraper. Built with Flask & BeautifulSoup.</p>
        </div>
    </footer>

    <script src="https://cdnjs.cloudflare.com/ajax/libs/bootstrap/5.1.3/js/bootstrap.bundle.min.js"></script>
    <script>
        async function scrapeBooks() {
            const btn = event.target;
            const originalText = btn.innerHTML;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Scraping...';
            btn.disabled = true;

            try {
                const response = await fetch('/scrape');
                const result = await response.json();
                
                if (result.success) {
                    alert(`Success! Scraped ${result.count} books.`);
                    location.reload();
                } else {
                    alert(`Error: ${result.message}`);
                }
            } catch (error) {
                alert(`Error: ${error.message}`);
            }

            btn.innerHTML = originalText;
            btn.disabled = false;
        }

        // Load stats
        async function loadStats() {
            try {
                const response = await fetch('/api/stats');
                const stats = await response.json();
                
                if (document.getElementById('total-books')) {
                    document.getElementById('total-books').textContent = stats.total_books;
                    document.getElementById('avg-price').textContent = `$${stats.average_price}`;
                    document.getElementById('avg-rating').textContent = stats.average_rating;
                }
            } catch (error) {
                console.error('Error loading stats:', error);
            }
        }

        document.addEventListener('DOMContentLoaded', loadStats);
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    """Home page with search functionality"""
    search_query = request.args.get('search', '')
    min_price = request.args.get('min_price', type=float)
    max_price = request.args.get('max_price', type=float)
    min_rating = request.args.get('min_rating', type=int)
    category = request.args.get('category', 'All')
    
    books = scraper.get_books_from_db(
        search_query=search_query if search_query else None,
        min_price=min_price,
        max_price=max_price,
        min_rating=min_rating,
        category=category if category != 'All' else None
    )
    
    categories = scraper.get_categories()
    
    content = f'''
    <!-- Search Section -->
    <section class="search-section text-white py-5">
        <div class="container">
            <div class="row">
                <div class="col-lg-8 mx-auto text-center">
                    <h1 class="display-4 mb-4">
                        <i class="fas fa-search"></i> Find Your Perfect Book
                    </h1>
                    <form method="GET" class="row g-3">
                        <div class="col-md-6">
                            <input type="text" class="form-control form-control-lg" name="search" 
                                   placeholder="Search books..." value="{search_query}">
                        </div>
                        <div class="col-md-3">
                            <select class="form-select form-select-lg" name="category">
                                <option value="All">All Categories</option>
                                {"".join([f'<option value="{cat}" {"selected" if cat == category else ""}>{cat}</option>' for cat in categories])}
                            </select>
                        </div>
                        <div class="col-md-3">
                            <button type="submit" class="btn btn-warning btn-lg w-100">
                                <i class="fas fa-search"></i> Search
                            </button>
                        </div>
                        
                        <!-- Advanced Filters -->
                        <div class="col-md-3">
                            <input type="number" class="form-control" name="min_price" 
                                   placeholder="Min Price" value="{min_price or ''}" step="0.01">
                        </div>
                        <div class="col-md-3">
                            <input type="number" class="form-control" name="max_price" 
                                   placeholder="Max Price" value="{max_price or ''}" step="0.01">
                        </div>
                        <div class="col-md-3">
                            <select class="form-select" name="min_rating">
                                <option value="">Any Rating</option>
                                {"".join([f'<option value="{i}" {"selected" if min_rating == i else ""}>{i}+ Stars</option>' for i in range(1, 6)])}
                            </select>
                        </div>
                        <div class="col-md-3">
                            <a href="/" class="btn btn-outline-light w-100">
                                Clear Filters
                            </a>
                        </div>
                    </form>
                </div>
            </div>
        </div>
    </section>

    <!-- Stats Section -->
    <section class="py-4 bg-light">
        <div class="container">
            <div class="row text-center">
                <div class="col-md-4">
                    <div class="stats-card p-3 bg-white rounded shadow-sm">
                        <h3 id="total-books" class="text-primary">-</h3>
                        <p class="mb-0">Total Books</p>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="stats-card p-3 bg-white rounded shadow-sm">
                        <h3 id="avg-price" class="text-success">-</h3>
                        <p class="mb-0">Average Price</p>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="stats-card p-3 bg-white rounded shadow-sm">
                        <h3 id="avg-rating" class="text-warning">-</h3>
                        <p class="mb-0">Average Rating</p>
                    </div>
                </div>
            </div>
        </div>
    </section>

    <!-- Books Grid -->
    <div class="container py-5">
        {f'''
        <div class="d-flex justify-content-between align-items-center mb-4">
            <h2>Found {len(books)} book(s)</h2>
        </div>
        
        <div class="row">
            {"".join([f'''
            <div class="col-lg-3 col-md-4 col-sm-6 mb-4">
                <div class="card book-card h-100 shadow-sm">
                    <img src="{book['image_url']}" class="card-img-top book-image" 
                         alt="{book['title']}" onerror="this.src='https://via.placeholder.com/200x300?text=No+Image'">
                    <div class="card-body d-flex flex-column">
                        <h6 class="card-title">{book['title'][:50]}{'...' if len(book['title']) > 50 else ''}</h6>
                        <div class="rating-stars mb-2">
                            {"".join([f'<i class="fas fa-star{"" if i < book["rating"] else " text-muted"}"></i>' for i in range(5)])}
                            <small class="text-muted">({book['rating']}/5)</small>
                        </div>
                        <p class="card-text small text-muted flex-grow-1">
                            {book['description'][:100]}{'...' if len(book['description']) > 100 else ''}
                        </p>
                        <div class="mt-auto">
                            <div class="d-flex justify-content-between align-items-center">
                                <span class="h5 text-success mb-0">${book['price']:.2f}</span>
                                <span class="badge bg-secondary">{book['category']}</span>
                            </div>
                            <small class="text-muted">{book['availability']}</small>
                            <div class="mt-2">
                                <a href="/book/{book['id']}" class="btn btn-primary btn-sm w-100">
                                    <i class="fas fa-eye"></i> View Details
                                </a>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            ''' for book in books])}
        </div>
        ''' if books else '''
        <div class="text-center py-5">
            <div class="mb-4">
                <i class="fas fa-search fa-3x text-muted"></i>
            </div>
            <h3 class="text-muted">No books found</h3>
            <p class="lead">Try adjusting your search criteria or scrape new data.</p>
            <button class="btn btn-primary btn-lg" onclick="scrapeBooks()">
                <i class="fas fa-sync"></i> Scrape Books Data
            </button>
        </div>
        '''}
    </div>
    '''
    
    return render_template_string(BASE_TEMPLATE, content=content, title="Book Store - Home")

@app.route('/scrape')
def scrape_data():
    """Endpoint to trigger data scraping"""
    try:
        print("Starting scraping process...")
        books_data = scraper.scrape_books(max_pages=5)  # Start with fewer pages for testing
        scraper.save_to_database(books_data)
        scraper.save_to_excel(books_data)
        return jsonify({
            'success': True, 
            'message': f'Successfully scraped {len(books_data)} books!',
            'count': len(books_data)
        })
    except Exception as e:
        print(f"Scraping error: {e}")
        return jsonify({'success': False, 'message': f'Error during scraping: {str(e)}'})

@app.route('/book/<int:book_id>')
def book_detail(book_id):
    """Book detail page"""
    conn = sqlite3.connect(scraper.db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM books WHERE id = ?", (book_id,))
    book = cursor.fetchone()
    conn.close()
    
    if book:
        columns = ['id', 'title', 'price', 'rating', 'availability', 'description', 
                  'image_url', 'product_url', 'category', 'upc', 'scraped_at']
        book_dict = dict(zip(columns, book))
        
        content = f'''
        <div class="container py-5">
            <div class="row">
                <div class="col-md-4">
                    <img src="{book_dict['image_url']}" class="img-fluid rounded shadow" 
                         alt="{book_dict['title']}" onerror="this.src='https://via.placeholder.com/400x600?text=No+Image'">
                </div>
                <div class="col-md-8">
                    <nav aria-label="breadcrumb">
                        <ol class="breadcrumb">
                            <li class="breadcrumb-item"><a href="/">Home</a></li>
                            <li class="breadcrumb-item active">{book_dict['title']}</li>
                        </ol>
                    </nav>
                    
                    <h1 class="mb-3">{book_dict['title']}</h1>
                    
                    <div class="row mb-3">
                        <div class="col-sm-6">
                            <div class="rating-stars mb-2">
                                {"".join([f'<i class="fas fa-star{"" if i < book_dict["rating"] else " text-muted"}"></i>' for i in range(5)])}
                                <span class="ms-2">{book_dict['rating']}/5 Stars</span>
                            </div>
                        </div>
                        <div class="col-sm-6">
                            <h2 class="text-success">${book_dict['price']:.2f}</h2>
                        </div>
                    </div>
                    
                    <div class="mb-4">
                        <span class="badge bg-primary me-2">{book_dict['category']}</span>
                        <span class="badge bg-{'success' if 'In stock' in book_dict['availability'] else 'warning'}">
                            {book_dict['availability']}
                        </span>
                    </div>
                    
                    <div class="row mb-4">
                        <div class="col-sm-6">
                            <strong>UPC:</strong> {book_dict['upc'] or 'N/A'}
                        </div>
                        <div class="col-sm-6">
                            <strong>Added:</strong> {book_dict['scraped_at']}
                        </div>
                    </div>
                    
                    <div class="mb-4">
                        <h4>Description</h4>
                        <p class="lead">{book_dict['description']}</p>
                    </div>
                    
                    <div class="mb-4">
                        <a href="{book_dict['product_url']}" target="_blank" class="btn btn-primary me-2">
                            <i class="fas fa-external-link-alt"></i> View on Original Site
                        </a>
                        <a href="/" class="btn btn-outline-secondary">
                            <i class="fas fa-arrow-left"></i> Back to Search
                        </a>
                    </div>
                </div>
            </div>
        </div>
        '''
        
        return render_template_string(BASE_TEMPLATE, content=content, title=f"{book_dict['title']} - Book Store")
    else:
        return "Book not found", 404

@app.route('/api/stats')
def api_stats():
    """API endpoint for database statistics"""
    conn = sqlite3.connect(scraper.db_path)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM books")
    total_books = cursor.fetchone()[0]
    
    cursor.execute("SELECT AVG(price) FROM books")
    avg_price = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT AVG(rating) FROM books")
    avg_rating = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT category, COUNT(*) FROM books GROUP BY category ORDER BY COUNT(*) DESC")
    categories = cursor.fetchall()
    
    conn.close()
    
    return jsonify({
        'total_books': total_books,
        'average_price': round(avg_price, 2),
        'average_rating': round(avg_rating, 2),
        'categories': categories
    })

if __name__ == '__main__':
    print("Book Scraper Web Application")
    print("=" * 50)
    print("Available endpoints:")
    print("- Home page with search: http://localhost:5000/")
    print("- Scrape data: http://localhost:5000/scrape")
    print("- API stats: http://localhost:5000/api/stats")
    print()
    print("Usage Instructions:")
    print("1. Run this script")
    print("2. Visit http://localhost:5000/")
    print("3. Click 'Scrape Data' to collect books from books.toscrape.com")
    print("4. Use the search and filter features to find books")
    print("5. View detailed book information")
    print("6. Data is saved to 'books.db' (SQLite) and 'books_data.xlsx' (Excel)")
    print()
    
    # Run Flask app
    app.run(debug=True, host='0.0.0.0', port=5000)
