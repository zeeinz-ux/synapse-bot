document.addEventListener('DOMContentLoaded', function() {

    const container = document.getElementById('music-player-container');
    let guildId = null;
    let pollInterval = null;

    /**
     * Ekstrak guild ID dari URL
     * Contoh: /dashboard/123456789/music/now-playing -> 123456789
     */
    function getGuildId() {
        const pathParts = window.location.pathname.split('/');
        const dashboardIndex = pathParts.indexOf('dashboard');
        if (dashboardIndex !== -1 && pathParts.length > dashboardIndex + 1) {
            return pathParts[dashboardIndex + 1];
        }
        return null;
    }

    /**
     * Fungsi utama untuk mengambil data dari API backend
     */
    async function fetchAndUpdate() {
        if (!guildId) {
            console.error("Guild ID tidak ditemukan di URL.");
            container.innerHTML = createErrorState('Gagal memuat pemutar musik. ID server tidak valid.');
            return;
        }

        try {
            const response = await fetch(`/api/music/status/${guildId}`);
            
            // Jika bot tidak online atau ada masalah server, tangani di sini
            if (!response.ok) {
                 if (pollInterval) clearInterval(pollInterval); // Hentikan polling
                 const errorData = await response.json().catch(() => null);
                 const message = errorData ? errorData.error : `Gagal terhubung ke server (Status: ${response.status}).`;
                 container.innerHTML = createErrorState(message);
                 return;
            }
            
            const state = await response.json();
            updateUI(state);

        } catch (error) {
            console.error("Gagal mengambil status musik:", error);
            container.innerHTML = createErrorState('Gagal terhubung ke bot. Pastikan bot online dan coba muat ulang halaman.');
            if (pollInterval) clearInterval(pollInterval);
        }
    }

    /**
     * Memperbarui UI berdasarkan data dari API
     */
    function updateUI(state) {
        // State 1: Bot tidak terhubung ke voice channel sama sekali.
        if (!state || !state.connected) {
            container.innerHTML = createEmptyState();
            if (pollInterval) clearInterval(pollInterval); // Stop polling karena tidak ada player aktif
            return;
        }

        // Jika UI pemutar musik belum ada, buat markupnya.
        let playerCard = container.querySelector('.player-card');
        if (!playerCard) {
            container.innerHTML = createPlayerMarkup();
        } 
        
        // State 2 & 3: Bot terhubung, baik sedang memutar lagu atau sedang idle.
        updatePlayerCard(state);
        updateQueueCard(state);
    }

    /**
     * Update bagian kartu pemutar musik utama
     */
    function updatePlayerCard(state) {
        const artwork = container.querySelector('.player-artwork img');
        const title = container.querySelector('.player-info h2');
        const author = container.querySelector('.player-info p');
        const progressFg = container.querySelector('.progress-bar-fg');
        const timeCurrent = container.querySelector('.time-current');
        const timeTotal = container.querySelector('.time-total');
        const playPauseBtnIcon = container.querySelector('.control-btn.play-pause i');

        // State 2: Ada lagu yang sedang diputar (atau dijeda)
        if (state.current_track) {
            artwork.src = state.current_track.artwork || '/static/img/default-artwork.png';
            artwork.alt = state.current_track.title;
            title.textContent = state.current_track.title;
            author.textContent = state.current_track.author;
            timeTotal.textContent = state.current_track.duration_fmt;
            timeCurrent.textContent = state.position_fmt;

            const progressPercent = (state.position_ms / state.current_track.duration_ms) * 100;
            progressFg.style.width = `${progressPercent}%`;
            
            if (state.paused) {
                playPauseBtnIcon.classList.remove('fa-pause');
                playPauseBtnIcon.classList.add('fa-play');
            } else {
                playPauseBtnIcon.classList.remove('fa-play');
                playPauseBtnIcon.classList.add('fa-pause');
            }
        // State 3: Tidak ada lagu (idle di voice channel)
        } else {
            artwork.src = '/static/img/default-artwork.png';
            artwork.alt = "No song playing";
            title.textContent = "Menunggu Lagu";
            author.textContent = "Gunakan /play untuk memulai musik";
            timeTotal.textContent = "0:00";
            timeCurrent.textContent = "0:00";
            progressFg.style.width = `0%`;
            playPauseBtnIcon.classList.remove('fa-pause');
            playPauseBtnIcon.classList.add('fa-play');
        }
    }

    /**
     * Update bagian kartu antrian
     */
    function updateQueueCard(state) {
        const queueCount = container.querySelector('.queue-count');
        const queueList = container.querySelector('.queue-list');

        queueCount.textContent = `${state.queue_count} lagu dalam antrian`;

        if (state.queue && state.queue.length > 0) {
            queueList.innerHTML = state.queue.map(track => `
                <li class="queue-item">
                    <span class="pos">${track.position}.</span>
                    <div class="queue-item-info">
                        <div class="title">${escapeHtml(track.title)}</div>
                        <div class="author">${escapeHtml(track.author)}</div>
                    </div>
                    <span class="duration">${track.duration_fmt}</span>
                </li>
            `).join('');
        } else {
            queueList.innerHTML = `
                <div class="queue-empty">
                    <i class="fas fa-list-ol"></i>
                    <p>Antrian kosong</p>
                </div>
            `;
        }
    }
    
    /**
     * Membuat markup HTML untuk seluruh player
     */
    function createPlayerMarkup() {
        return `
        <div class="player-card">
            <div class="player-artwork">
                <img src="/static/img/default-artwork.png" alt="Album Art">
            </div>
            <div class="player-info">
                <h2>Memuat...</h2>
                <p>...</p>
            </div>
            <div class="progress-bar-container">
                <div class="progress-bar-bg">
                    <div class="progress-bar-fg"></div>
                </div>
                <div class="progress-bar-time">
                    <span class="time-current">0:00</span>
                    <span class="time-total">0:00</span>
                </div>
            </div>
            <div class="player-controls">
                <button class="control-btn loop" title="Loop (segera hadir)" disabled><i class="fas fa-sync-alt"></i></button>
                <button class="control-btn prev" title="Previous (segera hadir)" disabled><i class="fas fa-step-backward"></i></button>
                <button class="control-btn play-pause" title="Play/Pause (segera hadir)" disabled><i class="fas fa-play"></i></button>
                <button class="control-btn next" title="Next (segera hadir)" disabled><i class="fas fa-step-forward"></i></button>
                <button class="control-btn shuffle" title="Shuffle (segera hadir)" disabled><i class="fas fa-random"></i></button>
            </div>
        </div>

        <div class="queue-card">
            <div class="queue-header">
                <h3>Berikutnya</h3>
                <span class="queue-count">0 lagu dalam antrian</span>
            </div>
            <ul class="queue-list">
                 <div class="queue-empty">
                    <i class="fas fa-spinner fa-spin"></i>
                 </div>
            </ul>
        </div>
        `;
    }

    /**
     * Membuat markup untuk state kosong (bot tidak di voice channel)
     */
    function createEmptyState() {
        return `
        <div class="player-loading" style="grid-column: 1 / -1;">
            <i class="fas fa-microphone-slash fa-3x" style="color: var(--text-secondary); margin-bottom: 1rem;"></i>
            <h2>Bot Tidak Terhubung</h2>
            <p>Hidden Hamlet tidak sedang berada di voice channel manapun.</p>
            <p style="font-size: 0.9rem; margin-top: 1rem;">Gunakan perintah <code>/play</code> di server Discord Anda untuk memulai sesi musik.</p>
        </div>
        `;
    }

    /**
     * Membuat markup untuk state error
     */
    function createErrorState(message) {
        return `
        <div class="player-loading" style="grid-column: 1 / -1;">
            <i class="fas fa-exclamation-triangle fa-3x" style="color: var(--accent-red); margin-bottom: 1rem;"></i>
            <h2>Oops! Terjadi Kesalahan</h2>
            <p>${escapeHtml(message)}</p>
        </div>
        `;
    }

    /**
     * Helper untuk escape HTML string untuk mencegah XSS
     */
    function escapeHtml(unsafe) {
        if (typeof unsafe !== 'string') return '';
        return unsafe
             .replace(/&/g, "&amp;")
             .replace(/</g, "&lt;")
             .replace(/>/g, "&gt;")
             .replace(/"/g, "&quot;")
             .replace(/'/g, "&#039;");
     }

    /**
     * Inisialisasi
     */
    function init() {
        guildId = getGuildId();
        if (guildId) {
            fetchAndUpdate(); // Panggil pertama kali untuk memuat UI awal
            // Hanya mulai polling jika panggilan pertama berhasil dan player ada
            setTimeout(() => {
                // Cek apakah player sudah dibuat, jika ya, mulai polling
                 if (container.querySelector('.player-card')) {
                    pollInterval = setInterval(fetchAndUpdate, 3000); // Polling setiap 3 detik
                }
            }, 1000); // Beri sedikit jeda sebelum memulai polling
        } else {
            container.innerHTML = createErrorState('Tidak dapat menemukan ID server dari URL. Pastikan Anda mengakses halaman ini dari dalam dashboard.');
        }
    }

    init();

});
