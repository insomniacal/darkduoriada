'use strict';

// Генерация случайного ID
function generateId(length = 12) {
    const chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
    let result = '';

    for (let i = 0; i < length; i++) {
        result += chars[Math.floor(Math.random() * chars.length)];
    }

    return result;
}

// Фейковый пользователь
const user = {
    id: Math.floor(Math.random() * 1000) + 1,
    name: `User_${Math.floor(Math.random() * 900 + 100)}`,
    sessionId: generateId(),
    createdAt: new Date().toISOString()
};

// Проверка
const isActive = user.sessionId.length >= 12;

// Имитация асинхронной операции
setTimeout(() => {
    console.log('User info:');
    console.log(user);
    console.log('Status:', isActive ? 'ACTIVE' : 'INACTIVE');
}, Math.random() * 2000);


console.log(Math.random())
