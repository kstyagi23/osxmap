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
  settings.client.subscribe?.((event) => {
    if (event.type === 'settings') {
      window.MERIDIAN_SERVICE_STATE = event.settings;
      window.dispatchEvent(new CustomEvent('meridian:service-settings', { detail: event.settings }));
    }
  });
  if (window.location.hash === '#settings') settings.open();
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initialize, { once: true });
else initialize();
