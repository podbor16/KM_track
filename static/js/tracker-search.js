// tracker-search.js — выбор участников и поиск

async function selectRunner(runnerId) {
    const runnerId_str = String(runnerId);

    if (selectedRunnerIds.size >= CONFIG.MAX_SELECTED) {
        alert(`❌ Максимум можно выбрать ${CONFIG.MAX_SELECTED} участников`);
        return;
    }
    if (selectedRunnerIds.has(runnerId_str)) {
        alert('✅ Этот участник уже отслеживается');
        return;
    }

    const runner = allRunners.find(r => String(r.id) === runnerId_str);
    if (!runner) {
        alert('❌ Участник не найден в базе');
        return;
    }

    selectedRunnerIds.add(runnerId_str);
    saveSelectedToStorage();

    if (runnerMarkers[runnerId_str]) {
        if (!map.hasLayer(runnerMarkers[runnerId_str])) {
            runnerMarkers[runnerId_str].addTo(map);
        }
    } else {
        createRunnerMarker(runner);
    }

    updateSelectedList();
    updateStatus(`✅ Отслеживание: ${runner.full_name} (${selectedRunnerIds.size}/${CONFIG.MAX_SELECTED})`);

    const resultsDiv = document.getElementById('searchResults');
    if (resultsDiv && resultsDiv.style.display !== 'none') {
        searchRunners();
    }
}

async function deselectRunner(runnerId) {
    const runnerId_str = String(runnerId);
    selectedRunnerIds.delete(runnerId_str);
    saveSelectedToStorage();

    if (runnerMarkers[runnerId_str]) {
        if (map.hasLayer(runnerMarkers[runnerId_str])) {
            map.removeLayer(runnerMarkers[runnerId_str]);
        }
        activePopups.delete(runnerId_str);
    }

    updateSelectedList();
    updateStatus(`Отслеживание остановлено (${selectedRunnerIds.size}/${CONFIG.MAX_SELECTED})`);
}

async function clearSelection() {
    if (!confirm('Удалить всех отслеживаемых участников?')) return;

    for (const runnerId of Array.from(selectedRunnerIds)) {
        await deselectRunner(runnerId);
    }
    clearSelectedStorage();
}

function updateSelectedList() {
    const selectedListDiv = document.getElementById('selectedList');
    if (!selectedListDiv) return;

    if (selectedRunnerIds.size === 0) {
        selectedListDiv.innerHTML = '<div style="color: #999; text-align: center; padding: 15px; font-size: 13px;">Нет отслеживаемых участников</div>';
        return;
    }

    let html = '<div style="padding: 8px; border: 1px solid #ddd; border-radius: 5px; max-height: 320px; overflow-y: auto; background: #f9f9f9;">';

    selectedRunnerIds.forEach(runnerId => {
        const runner = allRunners.find(r => String(r.id) === String(runnerId));
        if (!runner) return;
        html += `
            <div style="padding: 8px; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; align-items: center; gap: 8px;">
                <div style="flex: 1; min-width: 0;">
                    <strong style="display: block; font-size: 13px;">№${runner.start_number}</strong>
                    <div style="font-size: 12px; font-weight: 500; color: #333; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${runner.full_name}</div>
                    <div style="font-size: 11px; color: #666;">${runner.category || ''}</div>
                </div>
                <button onclick="deselectRunner('${runnerId}')" style="padding: 3px 6px; background: #f0f0f0; border: 1px solid #ccc; border-radius: 3px; cursor: pointer; font-size: 12px; white-space: nowrap;">✕</button>
            </div>
        `;
    });

    html += '</div>';
    html += `<button onclick="clearSelection()" style="margin-top: 8px; padding: 6px 10px; background: #fff3cd; border: 1px solid #ffc107; border-radius: 3px; cursor: pointer; width: 100%; font-size: 12px;">🗑️ Очистить (${selectedRunnerIds.size}/${CONFIG.MAX_SELECTED})</button>`;

    selectedListDiv.innerHTML = html;
}

function searchRunners() {
    const query = document.getElementById('searchInput');
    if (!query) return;

    const searchText = query.value.trim().toLowerCase();
    const resultsDiv = document.getElementById('searchResults');

    if (!searchText) {
        resultsDiv.innerHTML = '';
        resultsDiv.style.display = 'none';
        return;
    }

    const results = allRunners.filter(runner =>
        runner.full_name.toLowerCase().includes(searchText) ||
        String(runner.start_number).includes(searchText)
    ).slice(0, 15);

    if (results.length === 0) {
        resultsDiv.innerHTML = '<div style="padding: 10px; color: #999;">❌ Участники не найдены</div>';
        resultsDiv.style.display = 'block';
        return;
    }

    let html = '<div style="max-height: 400px; overflow-y: auto;">';

    results.forEach(runner => {
        const isSelected  = selectedRunnerIds.has(String(runner.id));
        const canSelect   = !isSelected && selectedRunnerIds.size < CONFIG.MAX_SELECTED;
        const statusColor = getStatusColor(runner.status);

        html += `
            <div style="padding: 10px; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; align-items: center;">
                <div style="flex: 1;">
                    <strong>№${runner.start_number}</strong> ${runner.full_name}
                    <div style="font-size: 11px; color: #666;">${runner.category || ''}</div>
                    <div style="font-size: 11px; color: ${statusColor}; margin-top: 3px;">● ${getStatusText(runner.status)}</div>
                </div>
                <button
                    onclick="selectRunner('${runner.id}')"
                    style="padding: 6px 12px;
                           background: ${isSelected ? '#90EE90' : canSelect ? '#EE2D62' : '#ccc'};
                           color: white;
                           border: none;
                           border-radius: 3px;
                           cursor: ${canSelect ? 'pointer' : 'not-allowed'};
                           font-weight: bold;"
                    ${!canSelect && !isSelected ? 'disabled' : ''}
                >
                    ${isSelected ? '✓' : '+'}
                </button>
            </div>
        `;
    });

    html += '</div>';
    resultsDiv.innerHTML = html;
    resultsDiv.style.display = 'block';
}

function setupSearch() {
    const searchInput = document.getElementById('searchInput');
    if (!searchInput) return;

    let searchTimeout;
    searchInput.addEventListener('input', () => {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(searchRunners, 300);
    });

    document.addEventListener('click', (event) => {
        const resultsDiv = document.getElementById('searchResults');
        if (resultsDiv && !searchInput.contains(event.target) && !resultsDiv.contains(event.target)) {
            resultsDiv.style.display = 'none';
        }
    });
}
