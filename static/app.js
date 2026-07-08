const tg = window.Telegram?.WebApp;
const placeholderImage = createPlaceholderSvg();

if (tg) {
    tg.ready();
    tg.expand();
}

const state = {
    categories: [
        { id: 1, name: 'Основные блюда' },
        { id: 2, name: 'Закуски' },
        { id: 3, name: 'Салаты' },
        { id: 4, name: 'Напитки' },
        { id: 5, name: 'Десерты' }
    ],
    products: [
        { id: 1, category_id: 1, name: 'Чизбургер', price: 40000, image: placeholderImage, prep_time: 15, popular: true },
        { id: 2, category_id: 1, name: 'Стейк из говядины', price: 98000, image: placeholderImage, prep_time: 25, popular: false },
        { id: 3, category_id: 2, name: 'Картофель фри', price: 22000, image: placeholderImage, prep_time: 10, popular: true },
        { id: 4, category_id: 2, name: 'Куриные крылья', price: 36000, image: placeholderImage, prep_time: 18, popular: true },
        { id: 5, category_id: 3, name: 'Цезарь с курицей', price: 35000, image: placeholderImage, prep_time: 12, popular: false },
        { id: 6, category_id: 3, name: 'Греческий салат', price: 28000, image: placeholderImage, prep_time: 9, popular: false },
        { id: 7, category_id: 4, name: 'Кола', price: 15000, image: placeholderImage, prep_time: 2, popular: true },
        { id: 8, category_id: 4, name: 'Лимонад', price: 18000, image: placeholderImage, prep_time: 4, popular: false },
        { id: 9, category_id: 5, name: 'Чизкейк', price: 26000, image: placeholderImage, prep_time: 6, popular: true },
        { id: 10, category_id: 5, name: 'Медовик', price: 24000, image: placeholderImage, prep_time: 7, popular: false }
    ],
    cart: new Map(),
    orderedItems: new Map(),
    activeCategoryId: 1,
    searchQuery: '',
    orderComment: '',
    tableNumber: null,
    submitting: false,
    drawerCollapsed: true
};

const elements = {
    root: document.documentElement,
    appShell: document.getElementById('appShell'),
    tableSelectorScreen: document.getElementById('tableSelectorScreen'),
    tableSelectorGrid: document.getElementById('tableSelectorGrid'),
    tableSelectorInput: document.getElementById('tableSelectorInput'),
    tableSelectorConfirm: document.getElementById('tableSelectorConfirm'),
    changeTableBtn: document.getElementById('changeTableBtn'),
    drawerToggle: document.getElementById('drawerToggle'),
    orderDrawer: document.getElementById('orderDrawer'),
    newOrderSound: document.getElementById('newOrderSound'),
    appToast: document.getElementById('appToast'),
    categoriesList: document.getElementById('categoriesList'),
    productsGrid: document.getElementById('productsGrid'),
    productsTitle: document.getElementById('productsTitle'),
    productsCounter: document.getElementById('productsCounter'),
    emptyState: document.getElementById('emptyState'),
    orderItems: document.getElementById('orderItems'),
    drawerSummary: document.getElementById('drawerSummary'),
    drawerTitle: document.getElementById('drawerTitle'),
    totalItems: document.getElementById('totalItems'),
    totalPrice: document.getElementById('totalPrice'),
    submitOrderBtn: document.getElementById('submitOrderBtn'),
    orderComment: document.getElementById('orderComment'),
    searchInput: document.getElementById('searchInput'),
    themeToggle: document.getElementById('themeToggle'),
    tableBadge: document.getElementById('tableBadge'),
    categoryTemplate: document.getElementById('categoryTemplate'),
    productTemplate: document.getElementById('productTemplate'),
    orderItemTemplate: document.getElementById('orderItemTemplate'),
    orderedItems: document.getElementById('orderedItems')
};

async function init() {
    applyTelegramTheme();
    bindEvents();
    renderTableSelector();
    hydrateTableFromSource();
    syncTableUI();
    await loadMenu();
    renderAll();
    updateMainButton();
}

function bindEvents() {
    elements.searchInput.addEventListener('input', (event) => {
        state.searchQuery = event.target.value.trim().toLowerCase();
        renderProducts();
    });

    elements.orderComment.addEventListener('input', (event) => {
        state.orderComment = event.target.value;
    });

    elements.themeToggle.addEventListener('click', toggleThemeMode);
    elements.submitOrderBtn.addEventListener('click', submitOrder);
    elements.drawerToggle.addEventListener('click', toggleDrawer);
    elements.changeTableBtn.addEventListener('click', openTableSelector);

    elements.tableSelectorConfirm.addEventListener('click', () => {
        const value = parseInt(elements.tableSelectorInput.value, 10);
        selectTable(value);
    });

    elements.tableSelectorInput.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
            const value = parseInt(elements.tableSelectorInput.value, 10);
            selectTable(value);
        }
    });

    if (tg?.MainButton) {
        tg.MainButton.onClick(submitOrder);
    }
}

function applyTelegramTheme() {
    const themeParams = tg?.themeParams || {};

    elements.root.dataset.theme = 'dark';

    setCssVar('--tg-bg', '#050816');
    setCssVar('--tg-secondary-bg', '#0b1220');
    setCssVar('--tg-text', '#f8fafc');
    setCssVar('--tg-hint', '#cbd5e1');
    setCssVar('--tg-accent', themeParams.button_color || '#22c55e');
    setCssVar('--tg-accent-strong', themeParams.button_color || '#16a34a');

    if (tg) {
        tg.setHeaderColor(themeParams.secondary_bg_color || '#0b1220');
        tg.setBackgroundColor(themeParams.bg_color || '#050816');
    }

    document.body.style.color = '#f8fafc';
}

function toggleThemeMode() {
    const isLight = elements.root.dataset.theme === 'light';
    elements.root.dataset.theme = isLight ? 'dark' : 'light';
    const newScheme = isLight ? 'dark' : 'light';
    document.body.style.color = newScheme === 'light' ? '#0f172a' : '#f8fafc';
    setCssVar('--tg-bg', newScheme === 'light' ? '#f5f7fb' : '#050816');
    setCssVar('--tg-secondary-bg', newScheme === 'light' ? '#ffffff' : '#0b1220');
    setCssVar('--tg-text', newScheme === 'light' ? '#0f172a' : '#f8fafc');
    setCssVar('--tg-hint', newScheme === 'light' ? '#64748b' : '#cbd5e1');
}

function setCssVar(name, value) {
    document.documentElement.style.setProperty(name, value);
}

function renderTableSelector() {
    elements.tableSelectorGrid.innerHTML = '';
    for (let table = 1; table <= 12; table += 1) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'table-selector-btn';
        button.textContent = `Стол ${table}`;
        button.classList.toggle('active', table === state.tableNumber);
        button.addEventListener('click', () => selectTable(table));
        elements.tableSelectorGrid.appendChild(button);
    }
}

function hydrateTableFromSource() {
    const detectedTable = getTableFromExternalSource();
    if (detectedTable) {
        state.tableNumber = detectedTable;
        elements.tableSelectorInput.value = String(detectedTable);
    }
}

function getTableFromExternalSource() {
    const rawStartParam = tg?.initDataUnsafe?.start_param;
    if (rawStartParam !== undefined && rawStartParam !== null) {
        const parsed = parseInt(String(rawStartParam).replace(/\D/g, ''), 10);
        if (!Number.isNaN(parsed) && parsed > 0) {
            return parsed;
        }
    }

    const queryValue = new URLSearchParams(window.location.search).get('table');
    if (queryValue) {
        const parsed = parseInt(String(queryValue).replace(/\D/g, ''), 10);
        if (!Number.isNaN(parsed) && parsed > 0) {
            return parsed;
        }
    }

    return null;
}

function selectTable(tableNumber) {
    if (!Number.isInteger(tableNumber) || tableNumber <= 0) {
        pulseHaptic('error');
        showErrorMessage('Укажите корректный номер стола.');
        return;
    }

    state.tableNumber = tableNumber;
    elements.tableSelectorInput.value = String(tableNumber);
    renderTableSelector();
    syncTableUI();
    pulseHaptic('light');
}

function openTableSelector() {
    elements.tableSelectorScreen.classList.remove('hidden');
    elements.appShell.classList.add('hidden');
    elements.orderDrawer.classList.add('hidden');
    elements.orderDrawer.classList.remove('expanded');
    state.drawerCollapsed = true;
}

function syncTableUI() {
    const hasTable = Number.isInteger(state.tableNumber) && state.tableNumber > 0;
    elements.tableBadge.textContent = hasTable ? `Стол ${state.tableNumber}` : 'Стол не выбран';
    elements.tableBadge.classList.toggle('error', !hasTable);
    elements.tableSelectorScreen.classList.toggle('hidden', hasTable);
    elements.appShell.classList.toggle('hidden', !hasTable);
    elements.drawerTitle.textContent = hasTable ? `Стол ${state.tableNumber}` : 'Стол';

    if (hasTable) {
        elements.orderDrawer.classList.remove('hidden');
        loadTableOrder(state.tableNumber);
    }
}

async function loadMenu() {
    try {
        const response = await fetch('/api/webapp/menu');
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();
        if (!data.success) {
            throw new Error(data.error || 'Не удалось загрузить меню');
        }

        if (Array.isArray(data.categories) && data.categories.length) {
            state.categories = data.categories;
            state.activeCategoryId = data.categories[0].id;
        }

        if (Array.isArray(data.products)) {
            state.products = data.products.map((product) => ({
                ...product,
                image: product.image || placeholderImage
            }));
        }
    } catch (error) {
        console.error('Load menu error:', error);
    }
}

async function loadTableOrder(tableNumber) {
    if (!tableNumber) return;

    try {
        const response = await fetch(`/api/webapp/table/${tableNumber}`);
        const data = await response.json();
        if (!response.ok || !data.success) {
            throw new Error(data.error || `HTTP ${response.status}`);
        }

        state.cart.clear();
        for (const item of data.items || []) {
            const matchedProduct = state.products.find((product) => product.name === item.item_name);
            if (!matchedProduct) continue;

            state.cart.set(matchedProduct.id, {
                id: matchedProduct.id,
                item_id: matchedProduct.id,
                name: matchedProduct.name,
                price: Number(item.item_price || matchedProduct.price || 0),
                quantity: Number(item.quantity || 0)
            });
        }

        state.orderedItems.clear();
        for (const item of data.ordered_items || []) {
            const matchedProduct = state.products.find((product) => product.name === item.item_name);
            if (!matchedProduct) continue;

            const existing = state.orderedItems.get(matchedProduct.id);
            const qty = Number(item.quantity || 0);
            state.orderedItems.set(matchedProduct.id, {
                quantity: (existing?.quantity || 0) + qty
            });
        }

        state.orderComment = data.comment || '';
        elements.orderComment.value = state.orderComment;
        renderProducts();
        renderCart();
    } catch (error) {
        console.error('Load table order error:', error);
    }
}

function renderAll() {
    renderCategories();
    renderProducts();
    renderCart();
    renderDrawerState();
}

function renderCategories() {
    elements.categoriesList.innerHTML = '';

    state.categories.forEach((category) => {
        const button = elements.categoryTemplate.content.firstElementChild.cloneNode(true);
        button.textContent = category.name;
        button.classList.toggle('active', category.id === state.activeCategoryId);
        button.addEventListener('click', () => {
            state.activeCategoryId = category.id;
            renderCategories();
            renderProducts();
        });
        elements.categoriesList.appendChild(button);
    });
}

function getVisibleProducts() {
    return state.products.filter((product) => {
        const matchesCategory = product.category_id === state.activeCategoryId;
        const matchesSearch = !state.searchQuery || product.name.toLowerCase().includes(state.searchQuery);
        return matchesCategory && matchesSearch;
    });
}

function renderProducts() {
    const visibleProducts = getVisibleProducts();
    const activeCategory = state.categories.find((category) => category.id === state.activeCategoryId);

    elements.productsGrid.innerHTML = '';
    elements.productsTitle.textContent = activeCategory?.name || 'Меню';
    elements.productsCounter.textContent = `${visibleProducts.length} блюд`;
    elements.emptyState.classList.toggle('hidden', visibleProducts.length > 0);

    visibleProducts.forEach((product) => {
        const card = elements.productTemplate.content.firstElementChild.cloneNode(true);
        const cartItem = state.cart.get(product.id);
        const quantity = cartItem?.quantity || 0;

        card.querySelector('.product-image').src = product.image;
        card.querySelector('.product-image').alt = product.name;
        card.querySelector('.product-name').textContent = product.name;
        card.querySelector('.product-meta').textContent = product.prep_time ? `⏱ ${product.prep_time} мин` : 'Готовится быстро';
        card.querySelector('.product-price').textContent = formatPrice(product.price);

        const orderedBadge = card.querySelector('.ordered-badge');
        const orderedItem = state.orderedItems.get(product.id);
        if (orderedItem) {
            orderedBadge.classList.remove('hidden');
            orderedBadge.textContent = `✓ ${orderedItem.quantity} шт`;
        } else {
            orderedBadge.classList.add('hidden');
        }

        const addButton = card.querySelector('.add-btn');
        const quickAddButton = card.querySelector('.quick-add-btn');
        const controls = card.querySelector('.quantity-controls');
        const qtyValue = card.querySelector('.qty-value');
        qtyValue.textContent = quantity;

        addButton.addEventListener('click', () => addToCart(product.id));
        quickAddButton.addEventListener('click', () => addToCart(product.id));
        controls.querySelector('[data-action="increase"]').addEventListener('click', () => changeQuantity(product.id, 1));
        controls.querySelector('[data-action="decrease"]').addEventListener('click', () => changeQuantity(product.id, -1));

        controls.classList.toggle('hidden', quantity === 0);
        addButton.classList.toggle('hidden', quantity > 0);

        elements.productsGrid.appendChild(card);
    });
}

function renderCart() {
    const orderedEntries = Array.from(state.orderedItems.entries());
    const entries = Array.from(state.cart.values());
    const totalItems = entries.reduce((sum, item) => sum + item.quantity, 0);
    const totalPrice = entries.reduce((sum, item) => sum + item.quantity * item.price, 0);

    const orderedContainer = elements.orderedItems;
    if (orderedContainer) {
        if (orderedEntries.length > 0) {
            orderedContainer.classList.remove('hidden');
            orderedContainer.innerHTML = `
                <div class="ordered-header">Заказано ранее</div>
                ${orderedEntries.map(([id, item]) => {
                    const product = state.products.find(p => p.id === id);
                    return product ? `
                        <div class="ordered-item">
                            <span class="ordered-item__name">${product.name}</span>
                            <span class="ordered-item__qty">×${item.quantity}</span>
                        </div>
                    ` : '';
                }).join('')}
            `;
        } else {
            orderedContainer.classList.add('hidden');
        }
    }

    elements.orderItems.innerHTML = '';

    if (entries.length === 0) {
        elements.orderItems.innerHTML = `
            <div class="order-empty">
                <div class="empty-icon">🧾</div>
                <p>Добавьте блюда, чтобы собрать заказ</p>
            </div>
        `;
    } else {
        entries.forEach((item) => {
            const orderItem = elements.orderItemTemplate.content.firstElementChild.cloneNode(true);
            orderItem.querySelector('.order-item__name').textContent = item.name;
            orderItem.querySelector('.order-item__price').textContent = `${formatPrice(item.price)} за шт.`;
            orderItem.querySelector('.order-item__total').textContent = formatPrice(item.quantity * item.price);
            orderItem.querySelector('.qty-value').textContent = item.quantity;
            orderItem.querySelector('[data-action="increase"]').addEventListener('click', () => changeQuantity(item.id, 1));
            orderItem.querySelector('[data-action="decrease"]').addEventListener('click', () => changeQuantity(item.id, -1));
            elements.orderItems.appendChild(orderItem);
        });
    }

    elements.drawerSummary.textContent = `${totalItems} позиций`;
    elements.totalItems.textContent = totalItems;
    elements.totalPrice.textContent = formatPrice(totalPrice);
    elements.submitOrderBtn.disabled = totalItems === 0 || state.submitting;

    updateMainButton(totalItems, totalPrice);
    renderDrawerState();
}

function renderDrawerState() {
    elements.orderDrawer.classList.toggle('collapsed', state.drawerCollapsed);
    elements.orderDrawer.classList.toggle('expanded', !state.drawerCollapsed);
    elements.drawerToggle.setAttribute('aria-label', state.drawerCollapsed ? 'Развернуть корзину' : 'Свернуть корзину');
}

function toggleDrawer() {
    state.drawerCollapsed = !state.drawerCollapsed;
    renderDrawerState();
}

function updateMainButton(totalItems = getCartTotals().items, totalPrice = getCartTotals().price) {
    if (!tg?.MainButton) return;

    if (totalItems > 0) {
        tg.MainButton.setText(`Отправить • ${totalItems} • ${formatPrice(totalPrice)}`);
        tg.MainButton.show();
        tg.MainButton.enable();
    } else {
        tg.MainButton.hide();
    }
}

function getCartTotals() {
    const entries = Array.from(state.cart.values());
    return {
        items: entries.reduce((sum, item) => sum + item.quantity, 0),
        price: entries.reduce((sum, item) => sum + item.quantity * item.price, 0)
    };
}

function addToCart(productId) {
    changeQuantity(productId, 1);
    pulseHaptic('light');
}

function changeQuantity(productId, delta) {
    const product = state.products.find((item) => item.id === productId);
    if (!product) return;

    const current = state.cart.get(productId);
    const nextQuantity = (current?.quantity || 0) + delta;

    if (nextQuantity <= 0) {
        state.cart.delete(productId);
    } else {
        state.cart.set(productId, {
            id: product.id,
            item_id: product.id,
            name: product.name,
            price: product.price,
            quantity: nextQuantity
        });
    }

    renderProducts();
    renderCart();
}

async function submitOrder() {
    if (state.submitting || state.cart.size === 0) return;

    const payload = buildOrderPayload();
    if (!payload.table_number) {
        pulseHaptic('error');
        showErrorMessage('Сначала выберите номер стола.');
        openTableSelector();
        return;
    }

    state.submitting = true;
    elements.submitOrderBtn.disabled = true;
    elements.submitOrderBtn.textContent = 'Отправка...';
    tg?.MainButton?.showProgress?.();

    try {
        const response = await fetch('/api/webapp/order', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        const result = await response.json();
        if (!response.ok || !result.success) {
            throw new Error(result.error || `HTTP ${response.status}`);
        }

        pulseHaptic('success');
        showToast(`Заказ по столу ${payload.table_number} отправлен`);
        if (elements.newOrderSound) {
            elements.newOrderSound.currentTime = 0;
            elements.newOrderSound.play().catch(() => {});
        }

        // Переносим отправленные позиции в orderedItems
        for (const [id, item] of state.cart) {
            const existing = state.orderedItems.get(id);
            state.orderedItems.set(id, {
                quantity: (existing?.quantity || 0) + item.quantity
            });
        }

        // Свернуть корзину и показать выбор стола
        state.drawerCollapsed = true;
        renderDrawerState();
        resetOrder();
        state.tableNumber = null;
        syncTableUI();
    } catch (error) {
        console.error('Submit order error:', error);
        pulseHaptic('error');
        showErrorMessage(error?.message || 'Не удалось отправить заказ. Попробуйте еще раз.');
    } finally {
        state.submitting = false;
        elements.submitOrderBtn.textContent = 'Отправить на кухню';
        tg?.MainButton?.hideProgress?.();
    }
}

function buildOrderPayload() {
    const cart = Array.from(state.cart.values()).map((item) => ({
        item_id: item.item_id,
        quantity: item.quantity
    }));

    return {
        table_number: state.tableNumber,
        waiter: tg?.initDataUnsafe?.user || null,
        comment: state.orderComment.trim(),
        cart
    };
}

function resetOrder() {
    state.cart.clear();
    state.orderComment = '';
    elements.orderComment.value = '';
    state.drawerCollapsed = true;
    renderAll();
}

function showErrorMessage(message) {
    if (tg?.showPopup) {
        tg.showPopup({
            title: 'Ошибка',
            message,
            buttons: [{ type: 'close' }]
        });
    } else {
        alert(message);
    }
}

function showToast(message) {
    if (!elements.appToast) return;
    elements.appToast.textContent = message;
    elements.appToast.classList.add('show');
    clearTimeout(showToast._timer);
    showToast._timer = setTimeout(() => {
        elements.appToast.classList.remove('show');
    }, 2600);
}

function pulseHaptic(type) {
    if (!tg?.HapticFeedback) return;

    if (type === 'success') {
        tg.HapticFeedback.notificationOccurred('success');
        return;
    }

    if (type === 'error') {
        tg.HapticFeedback.notificationOccurred('error');
        return;
    }

    tg.HapticFeedback.impactOccurred(type);
}

function formatPrice(value) {
    return `${Number(value || 0).toLocaleString('ru-RU')} сум`;
}

function createPlaceholderSvg() {
    const svg = `
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 280">
            <defs>
                <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
                    <stop offset="0%" stop-color="#22c55e" stop-opacity="0.9" />
                    <stop offset="100%" stop-color="#0f172a" stop-opacity="0.95" />
                </linearGradient>
            </defs>
            <rect width="400" height="280" rx="28" fill="url(#bg)" />
            <circle cx="118" cy="128" r="54" fill="rgba(255,255,255,0.16)" />
            <circle cx="118" cy="128" r="24" fill="rgba(255,255,255,0.38)" />
            <rect x="190" y="92" width="130" height="18" rx="9" fill="rgba(255,255,255,0.34)" />
            <rect x="190" y="124" width="92" height="14" rx="7" fill="rgba(255,255,255,0.2)" />
            <rect x="190" y="152" width="72" height="14" rx="7" fill="rgba(255,255,255,0.2)" />
        </svg>
    `;

    return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`;
}

init();
