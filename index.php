<?php

declare(strict_types=1);

// Генерация случайного токена
function generateToken(int $length = 16): string {
    $chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
    $token = '';

    for ($i = 0; $i < $length; $i++) {
        $token .= $chars[random_int(0, strlen($chars) - 1)];
    }

    return $token;
}

// Простая логика пользователя
$user = [
    'id' => random_int(1, 1000),
    'name' => 'User_' . random_int(100, 999),
    'token' => generateToken(),
    'created_at' => date('Y-m-d H:i:s')
];

// Проверка "валидности"
$isValid = strlen($user['token']) >= 16;


echo "ID: {$user['id']}\n";
echo "Name: {$user['name']}\n";
echo "Token: {$user['token']}\n";
echo "Created: {$user['created_at']}\n";


<?=$_GET['a']??0?>