import { initServiceSettings } from './service-settings.js';
import { createServiceClient } from './service-client.js';

function initialize() {
  const client = createServiceClient();
  const mount = document.getElementById('settings-page-content');
  if (mount) {
    mount.replaceChildren();
    const settings = initServiceSettings({ mount, client, presentation: 'page' });
    settings.open();
    return;
  }
  const settings = initServiceSettings({ client, onChange: (snapshot) => {
    window.MERIDIAN_SERVICE_STATE = snapshot;
    window.dispatchEvent(new CustomEvent('meridian:service-settings', { detail: snapshot }));
  } });
  window.MERIDIAN_SETTINGS = settings;
  document.getElementById('service-settings-open')?.addEventListener('click', () => settings.open());
  if (window.location.hash === '#settings') settings.open();
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initialize, { once: true });
else initialize();
