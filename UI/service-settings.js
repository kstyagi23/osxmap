import { createServiceClient } from './service-client.js';

export function initServiceSettings({ apiBase, mount = document.body, client = createServiceClient({ apiBase }), onChange = () => {}, presentation = 'dialog' } = {}) {
  const doc = mount.ownerDocument, page = presentation === 'page';
  const element = (tag, text, className) => {
    const node = doc.createElement(tag);
    if (text !== undefined) node.textContent = String(text);
    if (className) node.className = className;
    return node;
  };
  const button = (text, className) => { const node = element('button', text, className); node.type = 'button'; return node; };
  const labeled = (parent, title, input) => {
    const label = element('label', undefined, input.type === 'checkbox' ? 'ss-check' : 'ss-field');
    label.append(element('span', title), input); parent.append(label); return input;
  };
  const readable = (value) => String(value || 'Unknown').replace(/_/g, ' ');
  const stateOf = (product) => snapshot.services.find((item) => item.id === product.id) || {};
  const isBlocked = (settings) => ['permission_blocked', 'incompatible_renderer', 'blocked'].includes(settings.state);
  const dialog = element(page ? 'section' : 'dialog', undefined, `service-settings ss-shell${page ? ' ss-page' : ''}`);
  dialog.setAttribute('aria-labelledby', 'service-settings-title');
  const header = element('header', undefined, 'ss-header'), title = element('div');
  const heading = element('h2', 'Service settings'); heading.id = 'service-settings-title';
  title.append(element('p', 'MERIDIAN / CONNECTIONS', 'ss-eyebrow'), heading, element('p', 'Choose what your workspace can use. Requests only run when you ask.', 'ss-subtitle'));
  const actions = element('div', undefined, 'ss-actions');
  const reloadButton = button('Refresh', 'ss-secondary'), closeButton = button('Close', 'ss-secondary');
  actions.append(reloadButton); if (!page) actions.append(closeButton);
  header.append(title, actions);
  const overview = element('div', undefined, 'ss-overview'); overview.setAttribute('aria-label', 'Service overview');
  const status = element('p', '', 'ss-status'); status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite');
  const recovery = element('div', undefined, 'ss-recovery'); recovery.hidden = true;
  recovery.append(element('p', 'Start the local Meridian backend, then refresh. If this tab uses a different origin, open Settings directly on the backend.'));
  try {
    const origin = new URL(client.apiOrigin || apiBase || doc.location?.origin);
    if (['http:', 'https:'].includes(origin.protocol) && ['localhost', '127.0.0.1', '[::1]'].includes(origin.hostname) && !origin.username && !origin.password) {
      const anchor = element('a', 'Open backend Settings'); anchor.href = `${origin.origin}/settings.html`; recovery.append(anchor);
    }
  } catch { /* An unknown backend origin is not a safe recovery link. */ }
  const workspace = element('div', undefined, 'ss-workspace'), sidebar = element('aside', undefined, 'ss-sidebar');
  sidebar.setAttribute('aria-label', 'Service catalogue');
  const search = element('input'); search.type = 'search'; search.placeholder = 'Search name, category, capability'; search.setAttribute('aria-label', 'Search services');
  const category = element('select'); category.setAttribute('aria-label', 'Service category');
  const filter = element('select'); filter.setAttribute('aria-label', 'Service status');
  for (const [value, label] of [['all', 'All statuses'], ['available', 'Available'], ['enabled', 'Enabled'], ['configuration', 'Needs configuration'], ['blocked', 'Blocked']]) {
    const option = element('option', label); option.value = value; filter.append(option);
  }
  filter.value = 'all';
  const filters = element('div', undefined, 'ss-filters'); filters.append(category, filter);
  const listHeading = element('p', '', 'ss-list-heading'), list = element('div', undefined, 'ss-list');
  list.setAttribute('aria-label', 'Matching services');
  sidebar.append(search, filters, listHeading, list);
  const detail = element('article', undefined, 'ss-detail'); detail.setAttribute('aria-label', 'Selected service settings');
  workspace.append(sidebar, detail); dialog.append(header, overview, status, recovery, workspace); mount.append(dialog);
  let catalogue = [], snapshot = { services: [] }, selectedId, opener, disposed = false, loading, busy = false;
  let credentialInputs = [];
  const clearCredentials = () => { credentialInputs.forEach(([, input]) => { input.value = ''; }); };
  function officialLink(parent, label, value) {
    try {
      const url = new URL(value);
      if (url.protocol !== 'https:' || url.username || url.password) return;
      const anchor = element('a', label); anchor.href = url.href; anchor.target = '_blank'; anchor.rel = 'noopener noreferrer'; parent.append(anchor);
    } catch { /* Unreviewed or malformed links are not navigable. */ }
  }
  async function perform(operation, success) {
    if (busy || disposed) return;
    busy = true; status.textContent = 'Saving service settings...';
    for (const control of dialog.querySelectorAll('button,input,select,textarea')) control.disabled = true;
    try {
      await operation(); snapshot = client.snapshot || await client.settings();
      if (!disposed) { status.textContent = success; recovery.hidden = true; onChange(snapshot); }
    } catch { if (!disposed) status.textContent = 'Unable to save. Refresh if settings changed elsewhere. Credentials are never shown in errors.'; }
    finally {
      busy = false;
      for (const control of [reloadButton, closeButton, search, category, filter]) control.disabled = false;
      render();
    }
  }
  function renderList() {
    list.replaceChildren();
    const query = search.value.trim().toLowerCase();
    const matches = catalogue.filter((product) => {
      const settings = stateOf(product);
      if (category.value && category.value !== 'all' && category.value !== product.category) return false;
      if (query && !`${product.id} ${product.name || ''} ${product.category} ${(product.capabilities || []).join(' ')}`.toLowerCase().includes(query)) return false;
      if (filter.value === 'available' && !['available', 'enabled'].includes(settings.state) && !settings.effective_enabled) return false;
      if (filter.value === 'enabled' && !settings.effective_enabled) return false;
      if (filter.value === 'configuration' && !['needs_credentials', 'needs_setup', 'disabled'].includes(settings.state)) return false;
      if (filter.value === 'blocked' && !isBlocked(settings)) return false;
      return true;
    });
    if (!matches.some((product) => product.id === selectedId)) {
      clearCredentials();
      selectedId = (matches.find((product) => !product.billing && !product.auth_fields?.length && !isBlocked(stateOf(product)) && (stateOf(product).effective_enabled || stateOf(product).state === 'available')) || matches[0])?.id;
    }
    listHeading.textContent = `${matches.length} of ${catalogue.length} services`;
    for (const product of matches) {
      const settings = stateOf(product), selected = selectedId === product.id;
      const row = button(undefined, `ss-service${selected ? ' ss-selected' : ''}`);
      row.setAttribute('aria-pressed', String(selected)); row.setAttribute('data-service-id', product.id);
      const identity = element('span', undefined, 'ss-service-name');
      identity.append(element('strong', product.name || product.id), element('span', `${readable(product.category)} / ${product.billing ? 'Billing applies' : 'See licence'}`, 'ss-service-meta'));
      row.append(identity, element('span', readable(settings.state), `ss-badge${isBlocked(settings) ? ' ss-badge-blocked' : settings.effective_enabled ? ' ss-badge-ready' : ''}`));
      row.addEventListener('click', () => {
        if (busy) return;
        clearCredentials(); selectedId = product.id; render();
        [...list.querySelectorAll('button')].find((node) => node.getAttribute?.('data-service-id') === product.id || node.attributes?.['data-service-id'] === product.id)?.focus();
      });
      list.append(row);
    }
    if (!matches.length) {
      list.append(element('p', 'No services match these filters.', 'ss-empty'));
      const reset = button('Clear filters', 'ss-secondary'); reset.addEventListener('click', () => { search.value = ''; category.value = filter.value = 'all'; render(); }); list.append(reset);
    }
  }
  function renderDetail() {
    clearCredentials(); credentialInputs = []; detail.replaceChildren();
    const product = catalogue.find((item) => item.id === selectedId);
    if (!product) { detail.append(element('h3', catalogue.length ? 'No matching service' : 'Your service workspace'), element('p', catalogue.length ? 'Clear a filter to select a service.' : 'Refresh to load the reviewed catalogue and authoritative backend settings.', 'ss-muted')); return; }
    const settings = stateOf(product), blocked = settings.state === 'permission_blocked';
    const intro = element('div', undefined, 'ss-detail-header');
    intro.append(element('p', readable(product.category), 'ss-eyebrow'), element('h3', product.name || product.id), element('p', product.id, 'ss-service-id'));
    const state = element('div', undefined, 'ss-state');
    state.append(element('span', readable(settings.state), `ss-badge${isBlocked(settings) ? ' ss-badge-blocked' : settings.effective_enabled ? ' ss-badge-ready' : ''}`), element('p', settings.effective_enabled ? 'Available to the workspace. No background requests are started.' : 'Not active in the workspace. Backend checks determine availability.'));
    intro.append(state); detail.append(intro);
    for (const reason of [...new Set([...(settings.reasons || []), ...(product.blockers || [])])]) detail.append(element('p', reason, 'ss-blocker'));
    const facts = element('dl', undefined, 'ss-facts');
    const fact = (label, value) => { const group = element('div'); group.append(element('dt', label), element('dd', value)); facts.append(group); };
    fact('Capabilities', (product.capabilities || []).map(readable).join(', ') || 'Not specified');
    fact('Attribution', typeof product.attribution === 'object' ? JSON.stringify(product.attribution) : product.attribution || 'Not specified');
    fact('Licence / eligibility', product.license || product.licence || product.eligibility || 'Review the official terms before use');
    fact('Access', (product.authentication || []).map(readable).join(', ') || 'No credential schema specified');
    fact('Requested / effective', `${settings.requested_enabled ? 'On' : 'Off'} / ${settings.effective_enabled ? 'On' : 'Off'}`);
    fact('Policy reviewed', product.verification_date || 'Unknown'); detail.append(facts);
    const terms = element('div', undefined, 'ss-links');
    (product.terms || []).forEach((url, index) => officialLink(terms, `Official terms${product.terms.length > 1 ? ` ${index + 1}` : ''}`, url)); detail.append(terms);
    if (product.setup_steps?.length) {
      const setup = element('details', undefined, 'ss-disclosure'); setup.append(element('summary', 'Setup and access prerequisites'));
      const steps = element('ol'); product.setup_steps.forEach((step) => steps.append(element('li', step))); setup.append(steps); detail.append(setup);
    }
    const form = element('form', undefined, 'ss-section'); form.append(element('h4', 'Workspace access'));
    const enabled = element('input'); enabled.type = 'checkbox'; enabled.checked = settings.requested_enabled === true; enabled.disabled = blocked;
    labeled(form, blocked ? 'Enablement locked by reviewed permissions' : 'Enable this service', enabled);
    if (blocked) form.append(element('p', 'This permission block cannot be overridden here. Review the access prerequisites above.', 'ss-muted'));
    const acknowledgements = [];
    for (const acknowledgement of product.acknowledgements || []) {
      const id = typeof acknowledgement === 'string' ? acknowledgement : acknowledgement.id;
      const input = element('input'); input.type = 'checkbox'; input.checked = (settings.acknowledged || []).includes(id);
      labeled(form, typeof acknowledgement === 'string' ? `I acknowledge: ${readable(id)}` : acknowledgement.label, input); acknowledgements.push([id, input]);
    }
    const controls = element('div', undefined, 'ss-control-grid');
    const priority = element('input'); priority.type = 'number'; priority.step = '1'; priority.min = '0'; priority.max = '100'; priority.value = settings.priority ?? 0;
    labeled(controls, 'Priority (lower first)', priority);
    const limitInputs = [];
    for (const [name, defaultLimit] of Object.entries(product.limits || {})) {
      if (typeof defaultLimit !== 'number') continue;
      const input = element('input'); input.type = 'number'; input.min = '0'; input.step = '1'; input.max = String(defaultLimit); input.value = settings.limits?.[name] ?? defaultLimit;
      labeled(controls, readable(name), input); limitInputs.push([name, input, defaultLimit]);
    }
    form.append(controls);
    const overage = element('input'); overage.type = 'checkbox'; overage.checked = settings.allow_overage === true;
    if (product.billing) labeled(form, 'Allow requests beyond local limits', overage);
    if (limitInputs.length || product.billing) form.append(element('p', 'Local counters do not guarantee zero charges or account-wide limits. Set billing caps with the provider.', 'ss-muted'));
    const save = button('Save settings', 'ss-primary'); save.type = 'submit'; form.append(save);
    form.addEventListener('submit', (event) => {
      event.preventDefault();
      if (!String(priority.value).trim() || !Number.isSafeInteger(Number(priority.value)) || Number(priority.value) < 0 || Number(priority.value) > 100 || limitInputs.some(([, input, max]) => !String(input.value).trim() || !Number.isSafeInteger(Number(input.value)) || Number(input.value) < 0 || Number(input.value) > max)) {
        status.textContent = 'Use a whole-number priority and quotas within the reviewed local limits. No request was sent.'; return;
      }
      const patch = { acknowledged: acknowledgements.filter(([, input]) => input.checked).map(([id]) => id), priority: Number(priority.value), limits: Object.fromEntries(limitInputs.map(([name, input]) => [name, Number(input.value)])), allow_overage: product.billing ? overage.checked : false };
      if (!blocked) patch.enabled = enabled.checked;
      perform(() => client.update(product.id, patch), 'Settings saved. No connection test was run.');
    }); detail.append(form);
    const credentials = settings.credentials || {}, authFields = product.auth_fields || [];
    const credentialSection = element('section', undefined, 'ss-section'); credentialSection.append(element('h4', 'Authentication'), element('p', credentials.configured ? `Configured via ${readable(credentials.source)}. Values are write-only.` : 'No credentials configured.', 'ss-muted'));
    if (authFields.length) {
      credentialSection.append(element('p', 'Replace the complete credential set below. Nothing is prefilled or saved in this browser. Environment credentials remain read-only.', 'ss-muted'));
      const credentialForm = element('form'), fields = element('div', undefined, 'ss-control-grid');
      for (const field of authFields) {
        const name = typeof field === 'string' ? field : field.name;
        const input = element('input'); input.type = 'password'; input.autocomplete = 'new-password'; input.name = name; input.value = ''; input.maxLength = typeof field === 'object' ? field.max_length || 4096 : 4096;
        input.required = typeof field === 'string' || field.required !== false;
        labeled(fields, `Replace ${typeof field === 'string' ? readable(field) : field.label || readable(name)}`, input); credentialInputs.push([name, input, field]);
      }
      const inputs = credentialInputs.slice(); credentialForm.append(fields);
      const replace = button('Replace credentials', 'ss-primary'); replace.type = 'submit'; credentialForm.append(replace);
      credentialForm.addEventListener('submit', (event) => {
        event.preventDefault();
        const invalid = inputs.some(([, input, field]) => (input.required && !input.value.trim()) || input.value.length > input.maxLength || (typeof field === 'object' && field.min_length && input.value.length < field.min_length));
        const values = Object.fromEntries(inputs.filter(([, input]) => input.value !== '').map(([name, input]) => [name, input.value]));
        inputs.forEach(([, input]) => { input.value = ''; });
        if (invalid || !Object.keys(values).length) { status.textContent = 'Enter every required credential field to replace the complete set. Fields have been cleared; no request was sent.'; return; }
        perform(() => client.replaceCredentials(product.id, values), 'Credentials replaced. No connection test was run.');
      }); credentialSection.append(credentialForm);
      const confirmDelete = element('input'); confirmDelete.type = 'checkbox'; labeled(credentialSection, 'Confirm deletion of saved credentials (environment values are unchanged)', confirmDelete);
      const remove = button('Delete saved credentials', 'ss-secondary'); remove.disabled = true;
      confirmDelete.addEventListener('change', () => { remove.disabled = busy || !confirmDelete.checked; });
      remove.addEventListener('click', () => { if (confirmDelete.checked) perform(() => client.deleteCredentials(product.id), 'Saved credentials deleted.'); }); credentialSection.append(remove);
    } else credentialSection.append(element('p', 'This service has no browser-configurable credential fields.', 'ss-muted'));
    detail.append(credentialSection);
    const testSection = element('section', undefined, 'ss-section'); testSection.append(element('h4', 'Test connection'), element('p', 'An explicit test may consume provider quota. It does not prove usable observations or start live updates.', 'ss-muted'));
    const preset = element('select'); preset.setAttribute('aria-label', 'Connection test query type');
    for (const [value, text] of [['point', 'Location'], ['area', 'Region'], ['records', 'Small record sample']]) { const option = element('option', text); option.value = value; preset.append(option); }
    preset.value = /weather|geocod/i.test(`${product.category} ${(product.capabilities || []).join(' ')}`) ? 'point' : /aircraft|traffic|imagery|satellite/i.test(`${product.category} ${(product.capabilities || []).join(' ')}`) ? 'area' : 'records';
    labeled(testSection, 'Query preset', preset);
    const queryFields = element('div', undefined, 'ss-control-grid'), queryInputs = {};
    const addQuery = (name, label, value, min, max) => {
      const input = element('input'); input.type = 'number'; input.step = 'any'; input.value = String(value); input.min = String(min); input.max = String(max);
      labeled(queryFields, label, input); queryInputs[name] = input;
    };
    const updateQueryFields = () => {
      queryFields.replaceChildren(); for (const name of Object.keys(queryInputs)) delete queryInputs[name];
      if (preset.value === 'point') { addQuery('latitude', 'Latitude', 40.7128, -90, 90); addQuery('longitude', 'Longitude', -74.006, -180, 180); }
      if (preset.value === 'area') { addQuery('west', 'West longitude', -74.1, -180, 180); addQuery('south', 'South latitude', 40.6, -90, 90); addQuery('east', 'East longitude', -73.9, -180, 180); addQuery('north', 'North latitude', 40.8, -90, 90); }
      addQuery('limit', 'Maximum results', 5, 1, 100);
    }; updateQueryFields(); preset.addEventListener('change', updateQueryFields); testSection.append(queryFields);
    const advanced = element('details', undefined, 'ss-disclosure'), testQuery = element('textarea'); testQuery.maxLength = 4096; testQuery.rows = 4; testQuery.placeholder = 'Optional typed query object';
    advanced.append(element('summary', 'Advanced query / local job JSON')); labeled(advanced, 'Override preset with bounded JSON (no URLs or credentials)', testQuery); testSection.append(advanced);
    const testButton = button('Test connection (may consume provider quota)', 'ss-secondary'); testButton.disabled = !settings.effective_enabled;
    testButton.addEventListener('click', () => {
      if (!settings.effective_enabled) return;
      let query;
      try {
        if (testQuery.value.trim()) { if (testQuery.value.length > 4096) throw new Error(); query = JSON.parse(testQuery.value); if (!query || Array.isArray(query) || typeof query !== 'object') throw new Error(); }
        else {
          for (const input of Object.values(queryInputs)) if (!input.value.trim() || !Number.isFinite(Number(input.value)) || Number(input.value) < Number(input.min) || Number(input.value) > Number(input.max)) throw new Error();
          if (!Number.isInteger(Number(queryInputs.limit.value))) throw new Error();
          query = { limit: Number(queryInputs.limit.value) };
          if (preset.value === 'point') Object.assign(query, { latitude: Number(queryInputs.latitude.value), longitude: Number(queryInputs.longitude.value) });
          if (preset.value === 'area') { query.bbox = ['west', 'south', 'east', 'north'].map((name) => Number(queryInputs[name].value)); if (query.bbox[0] >= query.bbox[2] || query.bbox[1] >= query.bbox[3]) throw new Error(); }
        }
      } catch { status.textContent = 'Check query coordinates, result limits or advanced JSON. No request was sent.'; return; }
      perform(() => client.test(product.id, query), 'Connection test completed. This is not proof of usable observations.');
    }); testSection.append(testButton);
    if (!settings.effective_enabled) testSection.append(element('p', 'Enablement and backend prerequisites must be satisfied before testing.', 'ss-muted'));
    if (product.implementation_status === 'connected_workflow') {
      const jobStatus = element('p'); jobStatus.setAttribute('role', 'status');
      const submit = button('Start local import / validation job', 'ss-secondary'), check = button('Check job', 'ss-secondary'), cancel = button('Cancel job', 'ss-secondary');
      check.disabled = cancel.disabled = true; let jobId;
      const run = async (operation) => {
        try { const job = await operation(); if (disposed) return; jobId = job.id; check.disabled = cancel.disabled = !jobId; jobStatus.textContent = `${readable(job.state)}. Results do not mutate the map workspace.`; }
        catch { jobStatus.textContent = 'Local job unavailable. Configure an operator-owned import root and hash-pinned source proof.'; }
      };
      submit.addEventListener('click', () => {
        let request;
        try { if (testQuery.value.length > 4096) throw new Error(); request = JSON.parse(testQuery.value); if (!request || Array.isArray(request) || typeof request !== 'object') throw new Error(); }
        catch { jobStatus.textContent = 'Use advanced JSON with operation, configured source_id and a regional bbox if applicable.'; advanced.open = true; return; }
        run(() => client.submitJob(product.id, request));
      });
      check.addEventListener('click', () => run(() => client.jobStatus(product.id, jobId))); cancel.addEventListener('click', () => run(() => client.cancelJob(product.id, jobId)));
      testSection.append(element('p', 'Local jobs accept configured source IDs, never file paths, URLs or licence claims. No automatic downloads or installs.', 'ss-muted'), submit, check, cancel, jobStatus);
    }
    detail.append(testSection);
    const metadata = element('details', undefined, 'ss-disclosure'); metadata.append(element('summary', 'Coverage and implementation details'), element('p', `Coverage: ${typeof product.coverage === 'object' ? JSON.stringify(product.coverage) : product.coverage || 'Not specified'}`), element('p', `Renderers: ${(product.renderers || []).join(', ') || 'Not specified'}`), element('p', `Implementation: ${readable(product.implementation_status)}`), element('p', `Default access: ${product.default_enabled ? 'Enabled' : 'Disabled'}`)); detail.append(metadata);
  }
  function render() {
    if (disposed) return;
    overview.replaceChildren();
    for (const [label, count] of [['Catalogue', catalogue.length], ['Enabled', snapshot.services.filter((item) => item.effective_enabled).length], ['Needs configuration', snapshot.services.filter((item) => ['needs_credentials', 'needs_setup'].includes(item.state)).length], ['Blocked', snapshot.services.filter(isBlocked).length]]) {
      const metric = element('div'); metric.append(element('strong', count), element('span', label)); overview.append(metric);
    }
    renderList(); renderDetail();
  }
  async function refresh() {
    if (disposed) return snapshot;
    if (loading) return loading;
    clearCredentials(); status.textContent = 'Loading reviewed service catalogue...';
    loading = (async () => {
      try {
        const [data, settings] = await Promise.all([client.catalogue(), client.settings()]);
        if (disposed) return snapshot;
        catalogue = data.services || []; snapshot = settings;
        const previous = category.value; category.replaceChildren();
        for (const name of ['all', ...[...new Set(catalogue.map((product) => product.category).filter(Boolean))].sort()]) { const option = element('option', name === 'all' ? 'All categories' : readable(name)); option.value = name; category.append(option); }
        category.value = [...category.options].some((option) => option.value === previous) ? previous : 'all';
        status.textContent = ''; recovery.hidden = true; render(); onChange(snapshot); return snapshot;
      } catch {
        if (!disposed) { status.textContent = 'Service settings unavailable. Your last loaded settings are unchanged.'; recovery.hidden = false; }
        return client.snapshot || snapshot;
      } finally { loading = null; }
    })(); return loading;
  }
  function close() { clearCredentials(); if (page) dialog.hidden = true; else if (dialog.open) dialog.close(); opener?.focus(); }
  closeButton.addEventListener('click', close); reloadButton.addEventListener('click', refresh);
  if (!page) {
    dialog.addEventListener('cancel', (event) => { event.preventDefault(); close(); });
    dialog.addEventListener('close', clearCredentials);
    dialog.addEventListener('keydown', (event) => {
      if (event.key !== 'Tab') return;
      const focusable = [...dialog.querySelectorAll('button,input,select,textarea,a[href],summary')].filter((node) => !node.disabled && !node.hidden && (!node.getClientRects || node.getClientRects().length));
      const first = focusable[0], last = focusable[focusable.length - 1];
      if (event.shiftKey && doc.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && doc.activeElement === last) { event.preventDefault(); first?.focus(); }
    });
  }
  for (const [control, event] of [[search, 'input'], [category, 'change'], [filter, 'change']]) control.addEventListener(event, () => { if (!busy) render(); });
  render();
  return {
    client, dialog, element: dialog, refresh, close,
    open() { if (disposed) return; opener = doc.activeElement; dialog.hidden = false; if (!page && !dialog.open) dialog.showModal(); search.focus(); return refresh(); },
    destroy() { clearCredentials(); disposed = true; if (!page && dialog.open) dialog.close(); dialog.remove(); },
  };
}
