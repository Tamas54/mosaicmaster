// UNIVERSAL FETCH INTERCEPTOR - Ensures all API calls use relative URLs
// This file prevents Mixed Content errors by converting HTTP API calls to relative URLs

(function() {
  console.log('🔧 FETCH INTERCEPTOR: Initializing universal fetch interceptor...');
  
  // Store original fetch
  const originalFetch = window.fetch;
  
  // Override global fetch
  window.fetch = function(url, options) {
    console.log('🔧 FETCH INTERCEPTOR: Original URL:', url);
    
    // If URL contains the production domain, strip it to make it relative
    if (typeof url === 'string' && url.includes('mosaicmaster-production.up.railway.app')) {
      url = url.replace(/https?:\/\/mosaicmaster-production\.up\.railway\.app/g, '');
      console.log('🔧 FETCH INTERCEPTOR: Stripped production domain, new URL:', url);
    }
    
    // Ensure API URLs are relative - MORE AGGRESSIVE PATTERN
    if (typeof url === 'string' && url.match(/^https?:\/\/.*\/api\//)) {
      url = url.replace(/^https?:\/\/[^\/]+/, '');
      console.log('🔧 FETCH INTERCEPTOR: Made API URL relative:', url);
    }
    
    // FORCE all API calls to be relative if they contain /api/
    if (typeof url === 'string' && url.includes('/api/') && !url.startsWith('/')) {
      url = '/' + url.replace(/^.*?\/api\//, 'api/');
      console.log('🔧 FETCH INTERCEPTOR: FORCED relative API URL:', url);
    }
    
    console.log('🔧 FETCH INTERCEPTOR: Final URL:', url);
    return originalFetch.call(this, url, options);
  };
  
  console.log('✅ FETCH INTERCEPTOR: Universal fetch interceptor loaded successfully!');
})();