import { useState } from 'react'
import './App.css'

// API base URL - change this for production
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface Verification {
  is_exact_match: boolean
  brand_match: boolean
  size_match: boolean
  color_match: boolean
  mismatches: string[]
}

interface ImageVerification {
  is_verified: boolean
  confidence: number
  brand_detected: boolean
  product_detected: boolean
  reasoning: string
}

interface Source {
  name: string
  url: string
  found_upc: boolean
}

interface ProductResult {
  upc: string
  brand: string
  product_name: string
  size: string | null
  color: string | null
  msrp: number | null
  image_url: string | null
  description: string | null
  confidence_score: number
  reasoning: string
  sources: Source[]
  verification: Verification | null
  image_verification: ImageVerification | null
}

interface CachedProduct {
  id: number
  upc: string
  brand: string
  product_name: string
  msrp: number | null
  confidence_score: number
  created_at: string
}

interface CacheResponse {
  count: number
  products: CachedProduct[]
}

type Tab = 'search' | 'cache'

function App() {
  const [tab, setTab] = useState<Tab>('search')
  
  // Search form state
  const [name, setName] = useState('')
  const [brand, setBrand] = useState('')
  const [upc, setUpc] = useState('')
  const [size, setSize] = useState('')
  const [color, setColor] = useState('')
  
  // Results state
  const [result, setResult] = useState<ProductResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  
  // Cache state
  const [cache, setCache] = useState<CacheResponse | null>(null)
  const [cacheLoading, setCacheLoading] = useState(false)

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    setResult(null)

    try {
      const response = await fetch(`${API_URL}/api/enrich`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name,
          brand_name: brand,
          upc,
          size: size || null,
          color: color || null,
        }),
      })

      if (!response.ok) {
        const err = await response.json()
        throw new Error(err.detail || 'Failed to enrich product')
      }

      const data = await response.json()
      setResult(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred')
    } finally {
      setLoading(false)
    }
  }

  const loadCache = async () => {
    setCacheLoading(true)
    try {
      const response = await fetch(`${API_URL}/api/cache`)
      const data = await response.json()
      setCache(data)
    } catch {
      setError('Failed to load cache')
    } finally {
      setCacheLoading(false)
    }
  }

  const clearCache = async () => {
    if (!confirm('Delete all cached products?')) return
    
    setCacheLoading(true)
    try {
      const response = await fetch(`${API_URL}/api/cache`, { method: 'DELETE' })
      const data = await response.json()
      alert(data.message)
      setCache({ count: 0, products: [] })
    } catch {
      setError('Failed to clear cache')
    } finally {
      setCacheLoading(false)
    }
  }

  return (
    <div className="container">
      <header>
        <h1>🔍 Highstock Product Lookup</h1>
        <p className="subtitle">Beauty product enrichment with AI verification</p>
      </header>

      <nav className="tabs">
        <button 
          className={tab === 'search' ? 'active' : ''} 
          onClick={() => setTab('search')}
        >
          Search Product
        </button>
        <button 
          className={tab === 'cache' ? 'active' : ''} 
          onClick={() => { setTab('cache'); loadCache(); }}
        >
          View Cache
        </button>
      </nav>

      {tab === 'search' && (
        <main>
          <form onSubmit={handleSearch} className="search-form">
            <div className="form-group">
              <label htmlFor="name">Product Name *</label>
              <input
                id="name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g., No Pressure Lip Liner - #1 - On the Rose"
                required
              />
            </div>

            <div className="form-group">
              <label htmlFor="brand">Brand *</label>
              <input
                id="brand"
                type="text"
                value={brand}
                onChange={(e) => setBrand(e.target.value)}
                placeholder="e.g., DIBS Beauty"
                required
              />
            </div>

            <div className="form-group">
              <label htmlFor="upc">UPC Code *</label>
              <input
                id="upc"
                type="text"
                value={upc}
                onChange={(e) => setUpc(e.target.value)}
                placeholder="e.g., 850029397809"
                required
                pattern="[0-9]{8,13}"
                title="UPC must be 8-13 digits"
              />
            </div>

            <div className="form-row">
              <div className="form-group">
                <label htmlFor="size">Size (optional)</label>
                <input
                  id="size"
                  type="text"
                  value={size}
                  onChange={(e) => setSize(e.target.value)}
                  placeholder="e.g., 30ml"
                />
              </div>

              <div className="form-group">
                <label htmlFor="color">Color/Shade (optional)</label>
                <input
                  id="color"
                  type="text"
                  value={color}
                  onChange={(e) => setColor(e.target.value)}
                  placeholder="e.g., #190"
                />
              </div>
            </div>

            <button type="submit" className="btn-primary" disabled={loading}>
              {loading ? 'Searching...' : '🔍 Search'}
            </button>
          </form>

          {error && <div className="error">{error}</div>}

          {result && (
            <div className="result">
              <div className="result-header">
                {result.image_url && (
                  <img 
                    src={result.image_url} 
                    alt={result.product_name}
                    className="product-image"
                  />
                )}
                <div className="result-info">
                  <h2>{result.brand}</h2>
                  <h3>{result.product_name}</h3>
                  {result.msrp && (
                    <p className="price">MSRP: ${result.msrp.toFixed(2)}</p>
                  )}
                  <div className={`confidence ${result.confidence_score >= 80 ? 'high' : result.confidence_score >= 50 ? 'medium' : 'low'}`}>
                    Confidence: {result.confidence_score}%
                  </div>
                </div>
              </div>

              {result.description && (
                <div className="section">
                  <h4>Description</h4>
                  <p>{result.description}</p>
                </div>
              )}

              {result.verification && (
                <div className="section">
                  <h4>Verification</h4>
                  <div className="badges">
                    <span className={`badge ${result.verification.brand_match ? 'success' : 'fail'}`}>
                      {result.verification.brand_match ? '✓' : '✗'} Brand
                    </span>
                    <span className={`badge ${result.verification.size_match ? 'success' : 'fail'}`}>
                      {result.verification.size_match ? '✓' : '✗'} Size
                    </span>
                    <span className={`badge ${result.verification.color_match ? 'success' : 'fail'}`}>
                      {result.verification.color_match ? '✓' : '✗'} Color
                    </span>
                  </div>
                </div>
              )}

              {result.image_verification && (
                <div className="section">
                  <h4>AI Image Verification</h4>
                  <p>
                    <span className={`badge ${result.image_verification.is_verified ? 'success' : 'fail'}`}>
                      {result.image_verification.is_verified ? '✓' : '✗'} Verified
                    </span>
                    {' '}
                    Confidence: {result.image_verification.confidence}%
                  </p>
                  <p className="small">{result.image_verification.reasoning}</p>
                </div>
              )}

              <div className="section">
                <h4>Sources ({result.sources.length})</h4>
                <ul className="sources">
                  {result.sources.map((source, i) => (
                    <li key={i}>
                      <strong>{source.name}</strong>
                      {source.found_upc && <span className="badge success">UPC ✓</span>}
                    </li>
                  ))}
                </ul>
              </div>

              <div className="section">
                <p className="small">{result.reasoning}</p>
              </div>
            </div>
          )}
        </main>
      )}

      {tab === 'cache' && (
        <main>
          <div className="cache-header">
            <h2>Cached Products</h2>
            <button onClick={clearCache} className="btn-danger" disabled={cacheLoading}>
              🗑️ Clear All Cache
            </button>
          </div>

          {cacheLoading && <p>Loading...</p>}

          {cache && (
            <>
              <p className="cache-count">{cache.count} product(s) cached</p>
              
              {cache.products.length === 0 ? (
                <p className="empty">No cached products. Search for a product to populate the cache.</p>
              ) : (
                <div className="cache-list">
                  {cache.products.map((product) => (
                    <div key={product.id} className="cache-item">
                      <div>
                        <strong>{product.brand}</strong> - {product.product_name}
                      </div>
                      <div className="cache-meta">
                        <span>UPC: {product.upc}</span>
                        {product.msrp && <span>MSRP: ${product.msrp.toFixed(2)}</span>}
                        <span>Score: {product.confidence_score}%</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </main>
      )}

      <footer>
        <p>Built for Highstock Assignment • Uses AI for image verification</p>
      </footer>
    </div>
  )
}

export default App
