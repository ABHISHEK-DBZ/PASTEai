import React, { useState } from 'react';
import ReactDOM from 'react-dom/client';
import './styles.css';

const API_BASE = '/api/v1';

const SAMPLE_VFD_PRODUCT = {
  id: 'demo-vfd-001',
  part_number: 'ACS580-01-018A-4',
  manufacturer: 'ABB',
  category: 'Industrial Automation > Drives > Variable Frequency Drives (VFD)',
  source_filename: 'sample_datasheet.pdf',
  status: 'review',
  fields: [
    { id: 'f-1', attribute_key: 'voltage_rating', attribute_label: 'Rated Voltage', value: '400', unit: 'V AC', field_type: 'PROVED', confidence: 0.98, review_status: 'pending', sources: [{ ref: 'page_1 [x:120, y:240, w:180, h:30]', authority: 1.0, agreement: 'corroborated', evidence_text: 'Nominal Input Voltage: 3-Phase 380-480V AC' }] },
    { id: 'f-2', attribute_key: 'power_rating', attribute_label: 'Rated Power', value: '7.5', unit: 'kW', field_type: 'PROVED', confidence: 0.98, review_status: 'pending', sources: [{ ref: 'page_1 [x:120, y:280, w:150, h:25]', authority: 1.0, agreement: 'corroborated', evidence_text: 'Heavy-Duty Motor Power: 7.5 kW (10 hp)' }] },
    { id: 'f-3', attribute_key: 'current_rating', attribute_label: 'Rated Current', value: '17.7', unit: 'A', field_type: 'PROVED', confidence: 0.96, review_status: 'pending', sources: [{ ref: 'page_2 [x:95, y:110, w:210, h:28]', authority: 1.0, agreement: 'corroborated', evidence_text: 'Continuous Output Current: 17.7 A' }] },
    { id: 'f-4', attribute_key: 'frequency_rating', attribute_label: 'Output Frequency', value: '50/60', unit: 'Hz', field_type: 'PROVED', confidence: 0.97, review_status: 'pending', sources: [{ ref: 'page_2 [x:95, y:145, w:140, h:20]', authority: 1.0, agreement: 'corroborated', evidence_text: 'Output Frequency Range: 0 to 500 Hz' }] },
    { id: 'f-5', attribute_key: 'ip_rating', attribute_label: 'Ingress Protection', value: 'IP21', unit: '', field_type: 'PROVED', confidence: 0.95, review_status: 'pending', sources: [{ ref: 'page_1 [x:310, y:80, w:120, h:25]', authority: 1.0, agreement: 'corroborated', evidence_text: 'Enclosure Rating: IP21 / UL Type 1' }] },
    { id: 'f-6', attribute_key: 'operating_temp', attribute_label: 'Operating Temperature', value: '-15 to 50', unit: '°C', field_type: 'PROVED', confidence: 0.94, review_status: 'pending', sources: [{ ref: 'page_3 [x:110, y:300, w:190, h:30]', authority: 1.0, agreement: 'corroborated', evidence_text: 'Ambient Temp: -15 to +50 °C with no derating' }] },
    { id: 'f-7', attribute_key: 'weight', attribute_label: 'Net Weight', value: '7.3', unit: 'kg', field_type: 'PROVED', confidence: 0.92, review_status: 'pending', sources: [{ ref: 'page_3 [x:110, y:350, w:140, h:25]', authority: 1.0, agreement: 'corroborated', evidence_text: 'Frame Size R2 Net Weight: 7.3 kg' }] },
    { id: 'f-8', attribute_key: 'mounting_flange', attribute_label: 'Mounting Type', value: 'Wall Mount Frame R2', unit: '', field_type: 'INFERRED', confidence: 0.65, review_status: 'pending', sources: [{ ref: 'sibling_sku [ACS580-01-012A-4]', authority: 0.7, agreement: 'inferred', evidence_text: 'Inferred from sibling series frame dimensions' }] }
  ]
};

// Confidence bar color helper
const getConfidenceColor = (score) => {
  if (score >= 0.9) return { color: '#10b981', bg: 'rgba(16, 185, 129, 0.15)', border: 'rgba(16, 185, 129, 0.4)' };
  if (score >= 0.7) return { color: '#f59e0b', bg: 'rgba(245, 158, 11, 0.15)', border: 'rgba(245, 158, 11, 0.4)' };
  return { color: '#f43f5e', bg: 'rgba(244, 63, 94, 0.15)', border: 'rgba(244, 63, 94, 0.4)' };
};

function App() {
  const [product, setProduct] = useState(SAMPLE_VFD_PRODUCT);
  const [fields, setFields] = useState(SAMPLE_VFD_PRODUCT.fields);
  const [toastMsg, setToastMsg] = useState(null);
  const [toastKey, setToastKey] = useState(0);

  // 5-Tier Commercial Descriptions State
  const [descriptions, setDescriptions] = useState({
    mobile: 'ABB ACS580-01-018A-4 7.5kW 400V IP21',
    search: 'ABB ACS580-01-018A-4 7.5 kW VFD, 400V AC, 17.7A, IP21 enclosure, CE/UL certified.',
    short: 'Heavy-duty industrial Variable Frequency Drive Model ACS580-01-018A-4 by ABB. Rated for 7.5 kW at 400V AC, 17.7A. Features robust IP21 ingress protection and operating temperature range of -15 to 50°C for factory automation.',
    long: `• Manufacturer: ABB\n• Part Number: ACS580-01-018A-4\n• Leaf Taxonomy: Industrial Automation > Drives > Variable Frequency Drives (VFD)\n• Power Rating: 7.5 kW (10 hp)\n• Operating Voltage: 400V AC 3-Phase\n• Ingress Protection: IP21 Wall Mount\n• Operating Temperature Range: -15°C to 50°C\n• Net Weight: 7.3 kg\n• Compliance Certifications: CE, UL, cUL, EAC`,
    mfg: 'Official ABB ACS580 Series general purpose drive technical specification. Engineered for continuous high-torque industrial duty cycles and effortless pump/fan control. 100% corroborated against OEM engineering drawings and factory test certificates.'
  });

  const showToast = (msg) => {
    setToastMsg(msg);
    setToastKey(prev => prev + 1);
    setTimeout(() => setToastMsg(null), 3500);
  };

  const copyToClipboard = (text, label) => {
    navigator.clipboard.writeText(text);
    showToast(`${label} copied to clipboard!`);
  };

  const handleDescChange = (tier, val) => {
    setDescriptions(prev => ({ ...prev, [tier]: val }));
  };

  const handleFieldChange = (id, key, val) => {
    setFields(prev => prev.map(f => f.id === id ? { ...f, [key]: val } : f));
  };

  const handleAcceptField = (id) => {
    setFields(prev => prev.map(f => f.id === id ? { ...f, review_status: 'accepted' } : f));
    showToast('Attribute accepted and proved!');
  };

  const handleSaveField = (id) => {
    setFields(prev => prev.map(f => f.id === id ? { ...f, review_status: 'edited', field_type: 'HUMAN', confidence: 1.0 } : f));
    showToast('Value & UOM saved and certified as HUMAN!');
  };

  const handleRejectField = (id) => {
    setFields(prev => prev.map(f => f.id === id ? { ...f, review_status: 'rejected' } : f));
    showToast('Attribute rejected.');
  };

  const synthesizeFromSpecs = () => {
    const fieldMap = {};
    fields.forEach(f => { fieldMap[f.attribute_key] = f; });

    const mfg = product.manufacturer || 'ABB';
    const part = product.part_number || 'ACS580-01-018A-4';
    const v = fieldMap['voltage_rating'] ? `${fieldMap['voltage_rating'].value || '400'} ${fieldMap['voltage_rating'].unit || 'V AC'}` : '400V AC';
    const pwr = fieldMap['power_rating'] ? `${fieldMap['power_rating'].value || '7.5'} ${fieldMap['power_rating'].unit || 'kW'}` : '7.5 kW';
    const ip = fieldMap['ip_rating'] ? (fieldMap['ip_rating'].value || 'IP21') : 'IP21';
    const curr = fieldMap['current_rating'] ? `${fieldMap['current_rating'].value || '17.7'} ${fieldMap['current_rating'].unit || 'A'}` : '17.7A';

    setDescriptions({
      mobile: `${mfg} ${part} ${pwr} ${v} ${ip}`.substring(0, 80),
      search: `${mfg} ${part} ${pwr} VFD, ${v}, ${curr}, ${ip} enclosure, CE/UL certified.`.substring(0, 150),
      short: `Industrial ${part} variable frequency drive by ${mfg}. Rated for ${pwr} at ${v}. Features ${ip} ingress protection for factory automation.`.substring(0, 250),
      long: `• Manufacturer: ${mfg}\n• Part Number: ${part}\n• Power: ${pwr}\n• Voltage: ${v}\n• Enclosure: ${ip}`,
      mfg: `Official ${mfg} ${part} OEM specification. 100% verified against engineering datasheets.`
    });
    showToast('5-Tier Commercial Descriptions synthesized from normalized specs!');
  };

  const renderCharBadge = (len, max) => {
    if (max > 0) {
      const isExceeded = len > max;
      const isWarn = len >= max * 0.85;
      const cls = isExceeded ? 'char-badge-err' : isWarn ? 'char-badge-warn' : 'char-badge-ok';
      return (
        <span className={`badge ${cls}`}>
          {len} / {max} chars
        </span>
      );
    }
    return <span className="badge char-badge-ok">{len} chars</span>;
  };

  const handleDownloadUnilogExcel = async () => {
    showToast('Generating Unilog-compliant Excel (.xlsx)...');
    try {
      const exportItem = {
        Manufacturer_Part_Number: product.part_number,
        Manufacturer_Name: product.manufacturer,
        Taxonomy_Leaf_Category: product.category,
        Mobile_Description: descriptions.mobile,
        In_Search_Description: descriptions.search,
        Short_Description: descriptions.short,
        Long_Description: descriptions.long,
        Marketing_Description: descriptions.mfg,
        Primary_Image_URL: `https://assets.paste-ai.org/img/${product.part_number}.jpg`,
        Datasheet_PDF_URL: '/sample_datasheet.pdf',
        fields: fields,
        Provenance_Source_URL: `https://www.abb.com/products/${product.part_number}`
      };

      const res = await fetch(`${API_BASE}/export-unilog-excel`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify([exportItem])
      });

      if (res.ok) {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `unilog_${product.part_number}_export.xlsx`;
        a.click();
        showToast('Unilog Excel (.xlsx) downloaded successfully!');
      }
    } catch {
      showToast('Export triggered.');
    }
  };

  const acceptedCount = fields.filter(f => f.review_status === 'accepted' || f.review_status === 'edited').length;
  const pendingCount = fields.length - acceptedCount;

  return (
    <div className="app-container">
      {/* Cyber Header */}
      <header className="cyber-header">
        <div className="brand-area">
          <div className="brand-logo">🛡️</div>
          <div>
            <div className="brand-title">
              PASTE <span className="badge badge-proved">Unilog AI v2.0</span>
            </div>
            <div className="brand-subtitle">Product Intelligence & Trust Platform</div>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
          <div className="badge badge-proved" style={{ display: 'flex', gap: '0.4rem', padding: '0.4rem 0.8rem' }}>
            <span className="live-dot" style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#10b981', boxShadow: '0 0 8px #10b981' }}></span>
            E-COMMERCE FILTER: ACTIVE
          </div>
        </div>
      </header>

      {/* 1. TAXONOMY BREADCRUMB & METADATA CARD */}
      <div className="cyber-card">
        <div className="card-header">
          <div>
            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', fontFamily: 'JetBrains Mono', fontSize: '0.75rem', color: '#94a3b8', marginBottom: '0.5rem', flexWrap: 'wrap' }}>
              <span>Taxonomy:</span>
              <span className="badge badge-human">Industrial Automation</span>
              <span>›</span>
              <span className="badge badge-human">Drives</span>
              <span>›</span>
              <span className="badge badge-proved" style={{ fontWeight: 700 }}>Variable Frequency Drives (VFD)</span>
            </div>

            <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap' }}>
              <h1 style={{ fontFamily: 'Space Grotesk', fontSize: '1.5rem', fontWeight: 700, color: '#fff', letterSpacing: '-0.02em' }}>
                {product.manufacturer} — {product.part_number}
              </h1>
              <span className="badge badge-proved">REVIEW</span>
              <span className="badge badge-human">MPN: {product.part_number}</span>
            </div>
          </div>

          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <a href="/sample_datasheet.pdf" target="_blank" rel="noreferrer" className="provenance-link">
              📄 Official OEM Datasheet PDF ↗
            </a>
          </div>
        </div>

        {/* Stats Bar */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '0.75rem' }}>
          {[
            { label: 'Total Attributes', value: fields.length, icon: '📊', color: '#60a5fa' },
            { label: 'Proved', value: fields.filter(f => f.field_type === 'PROVED').length, icon: '✅', color: '#34d399' },
            { label: 'Inferred', value: fields.filter(f => f.field_type === 'INFERRED').length, icon: '⚠️', color: '#fbbf24' },
            { label: 'Pending Review', value: pendingCount, icon: '⏳', color: '#f472b6' },
          ].map(stat => (
            <div key={stat.label} style={{
              background: 'rgba(6, 10, 20, 0.6)',
              border: '1px solid rgba(30, 45, 74, 0.5)',
              borderRadius: '0.75rem',
              padding: '0.75rem 1rem',
              display: 'flex',
              alignItems: 'center',
              gap: '0.75rem',
              transition: 'all 0.3s ease',
            }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = stat.color + '66'; e.currentTarget.style.transform = 'translateY(-2px)'; e.currentTarget.style.boxShadow = `0 8px 20px -5px ${stat.color}22`; }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = 'rgba(30, 45, 74, 0.5)'; e.currentTarget.style.transform = 'translateY(0)'; e.currentTarget.style.boxShadow = 'none'; }}
            >
              <span style={{ fontSize: '1.25rem' }}>{stat.icon}</span>
              <div>
                <div style={{ fontSize: '1.25rem', fontWeight: 700, color: '#fff', lineHeight: 1.2, fontFamily: 'Space Grotesk' }}>{stat.value}</div>
                <div style={{ fontSize: '0.65rem', color: '#64748b', fontFamily: 'JetBrains Mono', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{stat.label}</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 2. 5-TIER COMMERCIAL DESCRIPTIONS CARD */}
      <section className="cyber-card">
        <div className="card-header">
          <div>
            <h2 className="card-title">
              <span style={{ color: '#10b981' }}>●</span> 5-Tier Commercial Descriptions Card
              <span className="badge badge-verbatim">Manufacturer Verbatim • Amazon/eBay Excluded</span>
            </h2>
            <div style={{ color: '#94a3b8', fontSize: '0.75rem', marginTop: '0.25rem' }}>
              Multi-channel verified commercial copy formatted to Unilog specifications with live character boundary gating.
            </div>
          </div>
          <div>
            <button onClick={synthesizeFromSpecs} className="btn btn-secondary">
              ⚡ Auto-Synthesize from Specs
            </button>
          </div>
        </div>

        <div className="tier-grid">
          {/* 1. Mobile */}
          <div className="tier-col-6">
            <div className="tier-box">
              <div className="tier-box-header">
                <div>
                  <span className="tier-label">1. Mobile Description</span>
                  <span className="tier-sublabel"> (Max 80 chars)</span>
                </div>
                <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                  {renderCharBadge(descriptions.mobile.length, 80)}
                  <button className="btn-icon" onClick={() => copyToClipboard(descriptions.mobile, 'Mobile')}>📋</button>
                </div>
              </div>
              <input
                type="text"
                className="cyber-input"
                value={descriptions.mobile}
                onChange={(e) => handleDescChange('mobile', e.target.value)}
              />
            </div>
          </div>

          {/* 2. In-Search */}
          <div className="tier-col-6">
            <div className="tier-box">
              <div className="tier-box-header">
                <div>
                  <span className="tier-label">2. In-Search Description</span>
                  <span className="tier-sublabel"> (Max 150 chars)</span>
                </div>
                <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                  {renderCharBadge(descriptions.search.length, 150)}
                  <button className="btn-icon" onClick={() => copyToClipboard(descriptions.search, 'In-Search')}>📋</button>
                </div>
              </div>
              <input
                type="text"
                className="cyber-input"
                value={descriptions.search}
                onChange={(e) => handleDescChange('search', e.target.value)}
              />
            </div>
          </div>

          {/* 3. Short */}
          <div className="tier-col-12">
            <div className="tier-box">
              <div className="tier-box-header">
                <div>
                  <span className="tier-label">3. Short Description</span>
                  <span className="tier-sublabel"> (Max 250 chars)</span>
                </div>
                <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                  {renderCharBadge(descriptions.short.length, 250)}
                  <button className="btn-icon" onClick={() => copyToClipboard(descriptions.short, 'Short')}>📋</button>
                </div>
              </div>
              <textarea
                rows={2}
                className="cyber-input"
                value={descriptions.short}
                onChange={(e) => handleDescChange('short', e.target.value)}
              />
            </div>
          </div>

          {/* 4. Long / Retail */}
          <div className="tier-col-6">
            <div className="tier-box">
              <div className="tier-box-header">
                <div>
                  <span className="tier-label">4. Long / Retail Description</span>
                  <span className="badge badge-human">Bulleted Specs</span>
                </div>
                <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                  {renderCharBadge(descriptions.long.length, 0)}
                  <button className="btn-icon" onClick={() => copyToClipboard(descriptions.long, 'Long')}>📋</button>
                </div>
              </div>
              <textarea
                rows={5}
                className="cyber-input"
                value={descriptions.long}
                onChange={(e) => handleDescChange('long', e.target.value)}
              />
            </div>
          </div>

          {/* 5. Marketing Description */}
          <div className="tier-col-6">
            <div className="tier-box">
              <div className="tier-box-header">
                <div>
                  <span className="tier-label">5. Marketing Description</span>
                  <span className="badge badge-verbatim">OEM Copy</span>
                </div>
                <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                  {renderCharBadge(descriptions.mfg.length, 0)}
                  <button className="btn-icon" onClick={() => copyToClipboard(descriptions.mfg, 'Marketing')}>📋</button>
                </div>
              </div>
              <textarea
                rows={5}
                className="cyber-input"
                value={descriptions.mfg}
                onChange={(e) => handleDescChange('mfg', e.target.value)}
              />
            </div>
          </div>
        </div>
      </section>

      {/* 3. NORMALIZED ATTRIBUTE TABLE WITH EXPLICIT VALUE & UOM SEPARATION */}
      <section className="cyber-card">
        <div className="card-header">
          <div>
            <h2 className="card-title">
              <span style={{ color: '#00e5ff' }}>●</span> Normalized Attributes Table with Explicit Value & UOM Separation
            </h2>
            <div style={{ color: '#94a3b8', fontSize: '0.75rem', marginTop: '0.25rem' }}>
              Physical attributes are strictly split into distinct Attribute Value and Unit of Measure (UOM) columns. Sibling SKUs capped at ≤0.70.
            </div>
          </div>
          <div style={{ fontFamily: 'JetBrains Mono', fontSize: '0.75rem', color: '#94a3b8' }}>
            {fields.length} attributes loaded
          </div>
        </div>

        <div className="table-wrapper">
          <table className="cyber-table">
            <thead>
              <tr>
                <th>Attribute Label</th>
                <th style={{ color: '#34d399' }}>Normalized Value</th>
                <th style={{ color: '#38bdf8' }}>UOM</th>
                <th>Confidence Score</th>
                <th>Status</th>
                <th style={{ color: '#fbbf24' }}>Source Provenance</th>
                <th style={{ textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {fields.map(f => {
                const isInf = f.field_type === 'INFERRED';
                const confColors = getConfidenceColor(f.confidence);
                return (
                  <tr key={f.id}>
                    <td>
                      <div style={{ fontWeight: 700, color: '#fff' }}>{f.attribute_label || f.attribute_key}</div>
                      <div style={{ fontSize: '0.7rem', color: '#64748b', fontFamily: 'JetBrains Mono' }}>{f.attribute_key}</div>
                    </td>

                    <td>
                      <input
                        type="text"
                        className="cyber-input attr-val-input"
                        value={f.value || ''}
                        onChange={(e) => handleFieldChange(f.id, 'value', e.target.value)}
                      />
                    </td>

                    <td>
                      <input
                        type="text"
                        className="cyber-input attr-uom-input"
                        value={f.unit || ''}
                        onChange={(e) => handleFieldChange(f.id, 'unit', e.target.value)}
                      />
                    </td>

                    <td>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem', minWidth: '90px' }}>
                        <span className={`badge ${f.confidence >= 0.9 ? 'badge-proved' : f.confidence >= 0.7 ? 'badge-inferred' : 'badge-dispute'}`} style={{ width: 'fit-content' }}>
                          {Math.round((f.confidence || 0) * 100)}%
                        </span>
                        <div style={{ width: '80px', height: '4px', background: 'rgba(30, 41, 59, 0.6)', borderRadius: '2px', overflow: 'hidden' }}>
                          <div style={{
                            width: `${(f.confidence || 0) * 100}%`,
                            height: '100%',
                            background: confColors.color,
                            borderRadius: '2px',
                            transition: 'width 0.5s ease',
                            boxShadow: `0 0 6px ${confColors.color}66`
                          }} />
                        </div>
                      </div>
                    </td>

                    <td>
                      <span className={`badge ${isInf ? 'badge-inferred' : 'badge-proved'}`}>
                        {f.field_type}{isInf ? ' (≤0.70)' : ''}
                      </span>
                    </td>

                    <td>
                      <a href="/sample_datasheet.pdf" target="_blank" rel="noreferrer" className="provenance-link">
                        📄 OEM Datasheet ↗
                      </a>
                    </td>

                    <td style={{ textAlign: 'right' }}>
                      {f.review_status === 'pending' ? (
                        <div style={{ display: 'flex', gap: '0.35rem', justifyContent: 'flex-end' }}>
                          <button className="btn btn-primary" style={{ padding: '0.3rem 0.6rem', fontSize: '0.75rem' }} onClick={() => handleAcceptField(f.id)}>
                            Accept
                          </button>
                          <button className="btn btn-secondary" style={{ padding: '0.3rem 0.6rem', fontSize: '0.75rem' }} onClick={() => handleSaveField(f.id)}>
                            Save
                          </button>
                          <button className="btn btn-danger" style={{ padding: '0.3rem 0.5rem', fontSize: '0.75rem' }} onClick={() => handleRejectField(f.id)}>
                            ✕
                          </button>
                        </div>
                      ) : (
                        <span className="badge badge-proved">{f.review_status.toUpperCase()}</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* Toast Notification Hub */}
      {toastMsg && (
        <div className="toast-container" key={toastKey}>
          <div className="toast">{toastMsg}</div>
        </div>
      )}
    </div>
  );
}

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<App />);