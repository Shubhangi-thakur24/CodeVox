/**
 * Vapi SDK Loader - Simplified for Mock
 */
(function() {
  console.log('🔍 Vapi SDK Loader starting...');
  
  const sdkText = document.getElementById('sdkText');
  
  // Check if Vapi already exists (from vapi.js loaded in HTML)
  function checkVapiLoaded() {
    return typeof window.Vapi !== 'undefined' && typeof window.Vapi === 'function';
  }
  
  // Wait for Vapi to be available
  window.loadVapiSDK = async function() {
    const maxAttempts = 50;
    
    for (let i = 0; i < maxAttempts; i++) {
      if (checkVapiLoaded()) {
        console.log('✅ Vapi SDK verified and ready');
        if (sdkText) {
          sdkText.textContent = 'Vapi SDK Ready';
          sdkText.style.color = 'var(--green)';
        }
        return true;
      }
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    
    console.error('❌ Vapi SDK failed to load after', maxAttempts, 'attempts');
    if (sdkText) {
      sdkText.textContent = 'SDK Load Failed - Check Console';
      sdkText.style.color = 'var(--red)';
    }
    return false;
  };
  
  // Auto-run
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => window.loadVapiSDK?.());
  } else {
    window.loadVapiSDK?.();
  }
})();