document.addEventListener('DOMContentLoaded', () => {
    const guildId = window.CURRENT_GUILD_ID;
    if (!guildId) {
        console.error('Error: Guild ID tidak ditemukan.');
        const queueList = document.getElementById('queue-list');
        if (queueList) {
            queueList.innerHTML = '<div class="queue-item-placeholder"><p>Error: Tidak dapat memuat antrian. Guild ID tidak valid.</p></div>';
        }
        return;
    }

    const queueList = document.getElementById('queue-list');
    const trackCountEl = document.getElementById('track-count');
    const totalDurationEl = document.getElementById('total-duration');
    const shuffleBtn = document.getElementById('shuffle-btn');
    const clearBtn = document.getElementById('clear-btn');

    const API_URL = `/api/music/status/${guildId}`;

    function formatDuration(ms) {
        const totalSeconds = Math.floor(ms / 1000);
        const hours = Math.floor(totalSeconds / 3600).toString().padStart(2, '0');
        const minutes = Math.floor((totalSeconds % 3600) / 60).toString().padStart(2, '0');
        const seconds = (totalSeconds % 60).toString().padStart(2, '0');
        return `${hours}:${minutes}:${seconds}`;
    }

    function renderQueue(state) {
        if (!queueList || !trackCountEl || !totalDurationEl) return;

        const tracks = state.queue || [];
        const totalDuration = tracks.reduce((acc, track) => acc + (track.duration_ms || 0), 0);

        trackCountEl.textContent = tracks.length;
        totalDurationEl.textContent = formatDuration(totalDuration);

        if (tracks.length === 0) {
            queueList.innerHTML = '<div class="queue-item-placeholder"><p>Antrian saat ini kosong.</p></div>';
            return;
        }

        let html = ''
        tracks.forEach((track, index) => {
            html += `
                <div class="queue-item" data-track-id="${track.id}">
                    <span class="track-position">${index + 1}</span>
                    <img src="${track.artwork || 'https://via.placeholder.com/48?text=Art'}" alt="Artwork" class="track-artwork">
                    <div class="track-details">
                        <p class="track-title">${track.title || 'Trek Tidak Dikenal'}</p>
                        <p class="track-author">${track.author || 'Artis Tidak Dikenal'}</p>
                    </div>
                    <span class="track-duration">${formatDuration(track.duration_ms || 0)}</span>
                    <div class="track-actions">
                        <button class="action-btn remove-track-btn" title="Hapus dari antrian">
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
                        </button>
                    </div>
                </div>
            `;
        });
        queueList.innerHTML = html;
    }

    async function fetchQueue() {
        try {
            const response = await fetch(API_URL);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const state = await response.json();
            renderQueue(state);
        } catch (error) {
            console.error("Gagal mengambil data antrian:", error);
            if (queueList) {
                queueList.innerHTML = '<div class="queue-item-placeholder"><p>Gagal memuat antrian. Coba lagi nanti.</p></div>';
            }
        }
    }

    // Event Listeners (untuk masa depan)
    if (shuffleBtn) {
        shuffleBtn.addEventListener('click', () => {
            console.log('Shuffle button clicked');
            // Logika untuk mengacak antrian akan ditambahkan di sini
        });
    }

    if (clearBtn) {
        clearBtn.addEventListener('click', () => {
            console.log('Clear button clicked');
            // Logika untuk membersihkan antrian akan ditambahkan di sini
        });
    }

    // Ambil data pertama kali & set interval untuk pembaruan
    fetchQueue();
    setInterval(fetchQueue, 5000); // refresh setiap 5 detik
});
