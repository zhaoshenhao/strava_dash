CREATE DATABASE strava_dash CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'strava_dash'@'%' IDENTIFIED BY 'strava_dash';
GRANT ALL PRIVILEGES ON *.* TO 'strava_dash'@'%';
FLUSH PRIVILEGES;