export function resolveApiBaseFromUrl(): string {
  try {
    const url = new URL(window.location.href);
    const override = url.searchParams.get('api');
    if (override) {
      const clean = override.replace(/\/$/, '');
      try { localStorage.setItem('THEIA_API_BASE', clean); } catch (_) {}
      return clean;
    }
  } catch (_) {}
  try {
    const saved = localStorage.getItem('THEIA_API_BASE');
    if (saved) return saved.replace(/\/$/, '');
  } catch (_) {}
  return '';
}

export async function loadApiBase(): Promise<string> {
  let API_BASE = resolveApiBaseFromUrl();
  if (API_BASE && API_BASE.startsWith('http')) return API_BASE;
  try {
    let apiBasePath = 'api-base.txt';
    if (window.location.hostname === 'storage.googleapis.com') {
      const parts = window.location.pathname.split('/');
      if (parts.length > 1 && parts[1]) apiBasePath = `/${parts[1]}/api-base.txt`;
    }
    const resp = await fetch(apiBasePath, { cache: 'no-store' });
    if (resp.ok) {
      const text = (await resp.text()).trim();
      if (text && text.startsWith('http')) {
        API_BASE = text.replace(/\/$/, '');
        try { localStorage.setItem('THEIA_API_BASE', API_BASE); } catch (_) {}
        return API_BASE;
      }
    }
  } catch (_) {}
  return 'https://theia-backend-v2-603965392227.us-central1.run.app';
}


