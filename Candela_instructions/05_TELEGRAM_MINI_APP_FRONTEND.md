# Frontend Telegram Mini App (React + Vite + Telegram WebApp SDK)

Этот документ описывает создание фронтенда витрины **Candela Home**: эстетику дизайна, интеграцию с нативным Telegram SDK, структуру компонентов и передачу авторизации.

---

## 1. Концепция дизайна и палитра (Разработано с Gemini)

Для бренда свечей и диффузоров ручной работы выбрана эстетика **«Теплый минимализм и тихая роскошь» (Warm Quiet Luxury)**:
* **Фон**: мягкий цвет айвори / теплого льна (`#FBF9F5` для светлой темы, `#181615` для темной темы Telegram).
* **Акцентные цвета**: теплый янтарный / терракотовый (`#C27848`), графитовый для текста (`#221F1E`), нежный шалфейный (`#8A9A86`).
* **Типографика**: элегантные заголовки с засечками (serif, e.g. *Playfair Display* или *Cormorant Garamond* для акцентов) и чистый гротеск для цен и кнопок (*Inter* / *Outfit*).
* **Тактильный отклик (Haptic Feedback)**: вибрация при клике на «Добавить в корзину» и смене количества товаров.

---

## 2. Инициализация Telegram WebApp SDK

Файл: `frontend_miniapp/src/telegram.ts`

```typescript
declare global {
  interface Window {
    Telegram?: {
      WebApp: any;
    };
  }
}

export const tg = typeof window !== 'undefined' ? window.Telegram?.WebApp : null;

export const initTelegramApp = () => {
  if (!tg) return;

  // Сообщаем клиенту Telegram о готовности приложения
  tg.ready();
  
  // Раскрываем окно Mini App на весь экран
  tg.expand();

  // Применяем цвета темы Telegram
  if (tg.themeParams) {
    document.documentElement.style.setProperty('--tg-bg-color', tg.themeParams.bg_color || '#FBF9F5');
    document.documentElement.style.setProperty('--tg-text-color', tg.themeParams.text_color || '#221F1E');
  }

  // Настройка кнопки назад
  tg.BackButton.onClick(() => {
    window.history.back();
  });
};

// Функция для вибрации смартфона
export const triggerHaptic = (type: 'light' | 'medium' | 'heavy' | 'success' | 'warning' = 'light') => {
  if (!tg?.HapticFeedback) return;
  if (type === 'success' || type === 'warning') {
    tg.HapticFeedback.notificationOccurred(type);
  } else {
    tg.HapticFeedback.impactOccurred(type);
  }
};

// Получение сырой строки initData для заголовка Authorization
export const getTelegramInitData = (): string => {
  return tg?.initData || '';
};
```

---

## 3. Архитектура React-компонентов

```text
frontend_miniapp/src/
├── api/
│   └── client.ts             # Axios/Fetch клиент с автоматическим заголовком Authorization: tma <initData>
├── components/
│   ├── Header.tsx            # Логотип Candela Home, поиск и переключатель категорий
│   ├── ProductCard.tsx       # Карточка товара: фото, название, объем, ноты, цена, кнопка в корзину
│   ├── AromaPyramid.tsx      # Визуальная ольфакторная пирамида аромата (Верх / Сердце / База)
│   ├── BottomNav.tsx         # Нижняя панель: Каталог, Корзина (с бейджем счетчика), Мои заказы
│   └── LegalDisclaimer.tsx   # Согласие 152-ФЗ, ссылка на оферту и правила пожарной безопасности
├── context/
│   └── CartContext.tsx       # Управление состоянием корзины (LocalStorage + синхронизация)
├── pages/
│   ├── CatalogPage.tsx       # Сетка товаров и фильтры по категориям (Свечи/Диффузоры/Саше)
│   ├── ProductDetailPage.tsx # Подробная информация, время горения, тип воска, галерея
│   ├── CartPage.tsx          # Список выбранных позиций и расчет суммы
│   ├── CheckoutPage.tsx      # Выбор доставки (СДЭК/Курьер), ввод адреса, согласие 152-ФЗ, кнопка «Оплатить»
│   └── OrderStatusPage.tsx   # Статус оформленного заказа
└── App.tsx
```

---

## 4. Компонент карточки с пирамидой аромата

Файл: `frontend_miniapp/src/components/AromaPyramid.tsx`

```tsx
import React from 'react';

interface AromaPyramidProps {
  pyramid: {
    top?: string[];
    heart?: string[];
    base?: string[];
  };
}

export const AromaPyramid: React.FC<AromaPyramidProps> = ({ pyramid }) => {
  return (
    <div className="bg-[#F4EFEB] dark:bg-[#252220] p-4 rounded-2xl my-4 text-sm">
      <h4 className="font-serif font-semibold text-[#8B5E3C] dark:text-[#E0A97E] mb-3 uppercase tracking-wider text-xs">
        Пирамида аромата
      </h4>
      
      {pyramid.top && pyramid.top.length > 0 && (
        <div className="mb-2">
          <span className="font-medium text-gray-500 text-xs">Верхние ноты:</span>
          <div className="flex flex-wrap gap-1.5 mt-1">
            {pyramid.top.map((note, i) => (
              <span key={i} className="px-2.5 py-0.5 bg-white dark:bg-[#342F2C] rounded-full text-xs shadow-sm">
                🍃 {note}
              </span>
            ))}
          </div>
        </div>
      )}

      {pyramid.heart && pyramid.heart.length > 0 && (
        <div className="mb-2">
          <span className="font-medium text-gray-500 text-xs">Ноты сердца:</span>
          <div className="flex flex-wrap gap-1.5 mt-1">
            {pyramid.heart.map((note, i) => (
              <span key={i} className="px-2.5 py-0.5 bg-white dark:bg-[#342F2C] rounded-full text-xs shadow-sm">
                🌸 {note}
              </span>
            ))}
          </div>
        </div>
      )}

      {pyramid.base && pyramid.base.length > 0 && (
        <div>
          <span className="font-medium text-gray-500 text-xs">Шлейф и база:</span>
          <div className="flex flex-wrap gap-1.5 mt-1">
            {pyramid.base.map((note, i) => (
              <span key={i} className="px-2.5 py-0.5 bg-white dark:bg-[#342F2C] rounded-full text-xs shadow-sm">
                🪵 {note}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
```

---

## 5. Экран оформления заказа (Checkout) с соблюдением 152-ФЗ

Файл: `frontend_miniapp/src/pages/CheckoutPage.tsx`

```tsx
import React, { useState } from 'react';
import { useCart } from '../context/CartContext';
import { getTelegramInitData, triggerHaptic, tg } from '../telegram';

export const CheckoutPage: React.FC = () => {
  const { cartItems, totalPrice, clearCart } = useCart();
  const [deliveryType, setDeliveryType] = useState('cdek_pvz');
  const [address, setAddress] = useState('');
  const [name, setName] = useState(tg?.initDataUnsafe?.user?.first_name || '');
  const [phone, setPhone] = useState('');
  const [email, setEmail] = useState('');
  const [pdConsent, setPdConsent] = useState(false); // Чекбокс согласия 152-ФЗ
  const [isLoading, setIsLoading] = useState(false);

  const handlePay = async () => {
    if (!pdConsent) {
      triggerHaptic('warning');
      alert('Необходимо дать согласие на обработку персональных данных (152-ФЗ)');
      return;
    }

    if (!address || !phone || !email) {
      alert('Пожалуйста, заполните все контактные данные');
      return;
    }

    setIsLoading(true);
    triggerHaptic('medium');

    try {
      const response = await fetch('/api/v1/orders', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `tma ${getTelegramInitData()}`
        },
        body: JSON.stringify({
          items: cartItems.map(item => ({ product_id: item.id, quantity: item.quantity })),
          delivery_type: deliveryType,
          delivery_address: address,
          recipient_name: name,
          recipient_phone: phone,
          recipient_email: email,
          pd_consent: pdConsent
        })
      });

      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Ошибка создания заказа');

      // Перенаправляем пользователя на защищенный платёжный шлюз ЮKassa
      if (data.payment_url) {
        clearCart();
        // Внутри Telegram WebApp открываем внешнюю ссылку через openLink
        if (tg?.openLink) {
          tg.openLink(data.payment_url);
        } else {
          window.location.href = data.payment_url;
        }
      }
    } catch (err: any) {
      alert(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="p-4 pb-24 max-w-lg mx-auto">
      <h2 className="text-2xl font-serif mb-4">Оформление заказа</h2>

      {/* Способ доставки */}
      <div className="mb-4">
        <label className="block text-sm font-medium mb-1">Способ доставки</label>
        <select 
          value={deliveryType} 
          onChange={(e) => setDeliveryType(e.target.value)}
          className="w-full p-3 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-[#252220]"
        >
          <option value="cdek_pvz">СДЭК (Пункт выдачи)</option>
          <option value="cdek_courier">СДЭК (Курьер до двери)</option>
          <option value="pochta_russia">Почта России</option>
          <option value="self_pickup">Самовывоз из мастерской</option>
        </select>
      </div>

      {/* Контактные поля */}
      <input 
        placeholder="ФИО получателя" 
        value={name} 
        onChange={(e) => setName(e.target.value)} 
        className="w-full p-3 mb-3 rounded-xl border bg-white dark:bg-[#252220]" 
      />
      <input 
        placeholder="Телефон (+7...)" 
        type="tel" 
        value={phone} 
        onChange={(e) => setPhone(e.target.value)} 
        className="w-full p-3 mb-3 rounded-xl border bg-white dark:bg-[#252220]" 
      />
      <input 
        placeholder="E-mail (для электронного чека 54-ФЗ)" 
        type="email" 
        value={email} 
        onChange={(e) => setEmail(e.target.value)} 
        className="w-full p-3 mb-3 rounded-xl border bg-white dark:bg-[#252220]" 
      />
      <textarea 
        placeholder="Адрес доставки или номер/адрес ПВЗ СДЭК" 
        value={address} 
        onChange={(e) => setAddress(e.target.value)} 
        className="w-full p-3 mb-4 rounded-xl border bg-white dark:bg-[#252220]" 
      />

      {/* Чекбокс согласия 152-ФЗ и Оферта */}
      <div className="flex items-start gap-2 mb-6">
        <input 
          type="checkbox" 
          id="pdConsent" 
          checked={pdConsent} 
          onChange={(e) => setPdConsent(e.target.checked)} 
          className="mt-1 w-4 h-4 rounded text-[#C27848]"
        />
        <label htmlFor="pdConsent" className="text-xs text-gray-500 leading-tight">
          Я согласен с условиями <a href="/privacy" className="underline text-[#C27848]">Политики конфиденциальности</a> и <a href="/offer" className="underline text-[#C27848]">Публичной оферты</a>, даю согласие на обработку персональных данных (152-ФЗ).
        </label>
      </div>

      {/* Кнопка оплаты */}
      <button 
        onClick={handlePay} 
        disabled={isLoading || !pdConsent}
        className="w-full py-4 bg-[#C27848] text-white font-medium rounded-2xl shadow-lg hover:opacity-90 disabled:opacity-50 transition"
      >
        {isLoading ? 'Подготовка оплаты...' : `Оплатить ${totalPrice} ₽`}
      </button>
    </div>
  );
};
```

---

## 6. Вкладки навигации (Bottom Navigation) и Профиль пользователя

В нижней части Mini App располагается постоянная фиксированная навигационная панель:
1. `Каталог` (Витрина ароматов, категории, пирамиды)
2. `Арома-ИИ` (Интерактивный квиз / AI-консультант)
3. `Корзина` (С динамическим индикатором количества товаров и списанием бонусов)
4. `Профиль` (Личный кабинет: статус Bronze/Silver/Gold, баланс бонусов, переключатель светлой/тёмной темы, история заказов, список покупок для оценки)

---

## 7. Эталонная геометрия шапки (Telegram Native Bar Alignment)

Для исключения конфликтов с нативными системными кнопками Telegram («✕ Закрыть» и «⌄ ⋮»):
1. **Шапка (Header):**
   * Минимальная высота: `min-h-[66px]`, отступ сверху `pt-5`.
   * Логотип `Candela HOME` расположен строго по центру на оптической оси системных кнопок с безопасными боковыми отступами (`px-24`).
2. **Поисковая строка:**
   * Располагается **строго под** системными кнопками с ощутимым воздушным зазором (`pt-3.5 pb-3`).
   * Форма: `rounded-full` (pill-shape в стиле UNICORN), плейсхолдер: `Найти в Candela Home` (исчезает при фокусе).
