-- phpMyAdmin SQL Dump
-- version 5.2.1
-- https://www.phpmyadmin.net/
--
-- Host: localhost:8889
-- Generation Time: Feb 13, 2026 at 05:02 PM
-- Server version: 8.0.40
-- PHP Version: 8.3.14

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;

--
-- Database: `tourgen_db`
--

-- --------------------------------------------------------

--
-- Table structure for table `amenity_master`
--

CREATE TABLE `amenity_master` (
  `id` int NOT NULL,
  `amenity_name` varchar(100) NOT NULL,
  `amenity_icon` varchar(100) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

--
-- Dumping data for table `amenity_master`
--

INSERT INTO `amenity_master` (`id`, `amenity_name`, `amenity_icon`) VALUES
(1, 'Free WiFi', 'bi-wifi'),
(2, 'AC', 'bi-snow'),
(3, 'Parking', 'bi-p-square'),
(4, 'Breakfast', 'bi-cup-hot'),
(5, 'Lift', 'bi-arrow-up-square'),
(6, 'Power Backup', 'bi-battery-charging'),
(7, 'TV', 'bi-tv'),
(8, '24x7 Check-in', 'bi-clock');

-- --------------------------------------------------------

--
-- Table structure for table `bookings`
--

CREATE TABLE `bookings` (
  `id` int NOT NULL,
  `user_id` int NOT NULL,
  `tour_id` int NOT NULL,
  `date` varchar(50) DEFAULT NULL,
  `status` varchar(50) DEFAULT 'pending'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

--
-- Dumping data for table `bookings`
--

INSERT INTO `bookings` (`id`, `user_id`, `tour_id`, `date`, `status`) VALUES
(8, 4, 11, '2026-2-17', 'paid'),
(9, 4, 12, '2026-02-10 12:35:20', 'paid'),
(10, 5, 13, '2026-02-10 13:13:02', 'paid'),
(11, 4, 14, '2026-02-10 13:32:11', 'paid'),
(12, 5, 12, '2026-02-10 13:43:08', 'paid'),
(13, 4, 11, '2026-02-12 21:49:20', 'pending'),
(14, 6, 11, '2026-02-12 22:01:40', 'paid');

-- --------------------------------------------------------

--
-- Table structure for table `booking_guide_requests`
--

CREATE TABLE `booking_guide_requests` (
  `id` int NOT NULL,
  `booking_id` int NOT NULL,
  `service_id` int DEFAULT NULL,
  `individual_requested` tinyint(1) DEFAULT '0',
  `note` varchar(255) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Table structure for table `cities`
--

CREATE TABLE `cities` (
  `id` int NOT NULL,
  `state_id` int DEFAULT NULL,
  `city_name` varchar(100) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

--
-- Dumping data for table `cities`
--

INSERT INTO `cities` (`id`, `state_id`, `city_name`) VALUES
(1, 1, 'Jaipur'),
(2, 2, 'Goa'),
(3, 3, 'Manali'),
(4, 1, 'Udaipur'),
(5, 4, 'Varanasi'),
(6, 10, 'Kuchh');

-- --------------------------------------------------------

--
-- Table structure for table `hotel_amenities`
--

CREATE TABLE `hotel_amenities` (
  `id` int NOT NULL,
  `service_id` int NOT NULL,
  `amenity_id` int NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

--
-- Dumping data for table `hotel_amenities`
--

INSERT INTO `hotel_amenities` (`id`, `service_id`, `amenity_id`) VALUES
(4, 1, 1),
(2, 1, 2),
(5, 1, 3),
(3, 1, 4),
(6, 1, 7),
(1, 1, 8);

-- --------------------------------------------------------

--
-- Table structure for table `hotel_bookings`
--

CREATE TABLE `hotel_bookings` (
  `id` int NOT NULL,
  `user_id` int NOT NULL,
  `service_id` int NOT NULL,
  `room_type_id` int NOT NULL,
  `check_in_date` date NOT NULL,
  `check_out_date` date NOT NULL,
  `rooms_booked` int NOT NULL,
  `guests_count` int NOT NULL,
  `nights` int NOT NULL,
  `total_amount` decimal(10,2) NOT NULL,
  `status` varchar(30) DEFAULT 'confirmed',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Table structure for table `hotel_images`
--

CREATE TABLE `hotel_images` (
  `id` int NOT NULL,
  `service_id` int NOT NULL,
  `image_url` varchar(255) NOT NULL,
  `image_title` varchar(120) DEFAULT NULL,
  `is_cover` tinyint(1) DEFAULT '0',
  `sort_order` int DEFAULT '0',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

--
-- Dumping data for table `hotel_images`
--

INSERT INTO `hotel_images` (`id`, `service_id`, `image_url`, `image_title`, `is_cover`, `sort_order`, `created_at`) VALUES
(10, 1, 'Hotel_01/h1_01.jpeg', 'Hotel Front', 1, 1, '2026-02-12 17:58:46'),
(11, 1, 'Hotel_01/h1_02.jpeg', 'Lobby', 0, 2, '2026-02-12 17:58:46'),
(12, 1, 'Hotel_01/h1_03.jpeg', 'Room View 1', 0, 3, '2026-02-12 17:58:46'),
(13, 1, 'Hotel_01/h1_04.jpeg', 'Room View 2', 0, 4, '2026-02-12 17:58:46'),
(14, 1, 'Hotel_01/h1_05.jpeg', 'Dining/Facility', 0, 5, '2026-02-12 17:58:46');

-- --------------------------------------------------------

--
-- Table structure for table `hotel_profiles`
--

CREATE TABLE `hotel_profiles` (
  `id` int NOT NULL,
  `service_id` int NOT NULL,
  `hotel_name` varchar(150) NOT NULL,
  `brand_name` varchar(120) DEFAULT NULL,
  `star_rating` tinyint DEFAULT '0',
  `address_line1` varchar(255) NOT NULL,
  `address_line2` varchar(255) DEFAULT NULL,
  `locality` varchar(120) DEFAULT NULL,
  `landmark` varchar(150) DEFAULT NULL,
  `pincode` varchar(15) DEFAULT NULL,
  `latitude` decimal(10,7) DEFAULT NULL,
  `longitude` decimal(10,7) DEFAULT NULL,
  `check_in_time` time DEFAULT NULL,
  `check_out_time` time DEFAULT NULL,
  `hotel_description` text,
  `house_rules` text,
  `couple_friendly` tinyint(1) DEFAULT '0',
  `pets_allowed` tinyint(1) DEFAULT '0',
  `parking_available` tinyint(1) DEFAULT '0',
  `breakfast_available` tinyint(1) DEFAULT '0',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

--
-- Dumping data for table `hotel_profiles`
--

INSERT INTO `hotel_profiles` (`id`, `service_id`, `hotel_name`, `brand_name`, `star_rating`, `address_line1`, `address_line2`, `locality`, `landmark`, `pincode`, `latitude`, `longitude`, `check_in_time`, `check_out_time`, `hotel_description`, `house_rules`, `couple_friendly`, `pets_allowed`, `parking_available`, `breakfast_available`, `created_at`, `updated_at`) VALUES
(1, 1, 'Hotel Royal Stay', 'Royal Group', 4, '123 Main Road', 'Near Bus Stand', 'Civil Lines', 'City Mall', '302001', 26.9124340, 75.7872710, '12:00:00', '11:00:00', 'Modern rooms with great service', 'Valid ID required. No loud music after 10 PM.', 1, 0, 1, 1, '2026-02-12 17:46:12', '2026-02-12 17:46:12');

-- --------------------------------------------------------

--
-- Table structure for table `hotel_reviews`
--

CREATE TABLE `hotel_reviews` (
  `id` int NOT NULL,
  `service_id` int NOT NULL,
  `user_id` int NOT NULL,
  `rating` decimal(2,1) NOT NULL,
  `review_text` text,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Table structure for table `hotel_room_inventory_logs`
--

CREATE TABLE `hotel_room_inventory_logs` (
  `id` int NOT NULL,
  `room_type_id` int NOT NULL,
  `changed_by` int NOT NULL,
  `old_available` int NOT NULL,
  `new_available` int NOT NULL,
  `note` varchar(255) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Table structure for table `hotel_room_types`
--

CREATE TABLE `hotel_room_types` (
  `id` int NOT NULL,
  `service_id` int NOT NULL,
  `room_type_name` varchar(120) NOT NULL,
  `bed_type` varchar(80) DEFAULT NULL,
  `room_size_sqft` int DEFAULT NULL,
  `max_guests` int DEFAULT '2',
  `total_rooms` int DEFAULT '0',
  `available_rooms` int DEFAULT '0',
  `base_price` decimal(10,2) NOT NULL,
  `strike_price` decimal(10,2) DEFAULT NULL,
  `tax_percent` decimal(5,2) DEFAULT '0.00',
  `breakfast_included` tinyint(1) DEFAULT '0',
  `ac_available` tinyint(1) DEFAULT '1',
  `wifi_available` tinyint(1) DEFAULT '1',
  `refundable` tinyint(1) DEFAULT '0',
  `cancellation_policy` varchar(255) DEFAULT NULL,
  `room_description` text,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

--
-- Dumping data for table `hotel_room_types`
--

INSERT INTO `hotel_room_types` (`id`, `service_id`, `room_type_name`, `bed_type`, `room_size_sqft`, `max_guests`, `total_rooms`, `available_rooms`, `base_price`, `strike_price`, `tax_percent`, `breakfast_included`, `ac_available`, `wifi_available`, `refundable`, `cancellation_policy`, `room_description`, `created_at`, `updated_at`) VALUES
(1, 1, 'Classic Room', 'Queen', 180, 2, 20, 14, 2499.00, 3199.00, 12.00, 0, 1, 1, 0, 'Free cancellation till 24 hrs before check-in', 'Cozy room for 2 guests', '2026-02-12 17:46:12', '2026-02-12 17:46:12'),
(2, 1, 'Deluxe Room', 'King', 240, 3, 12, 8, 3299.00, 4199.00, 12.00, 1, 1, 1, 1, 'Partially refundable', 'Bigger room with city view', '2026-02-12 17:46:12', '2026-02-12 17:46:12'),
(3, 1, 'Family Suite', 'King + Sofa', 360, 5, 6, 3, 4999.00, 5999.00, 12.00, 1, 1, 1, 1, 'Refundable with deduction', 'Suite ideal for family stays', '2026-02-12 17:46:12', '2026-02-12 17:46:12');

-- --------------------------------------------------------

--
-- Table structure for table `master_spots`
--

CREATE TABLE `master_spots` (
  `id` int NOT NULL,
  `spot_name` varchar(100) DEFAULT NULL,
  `image_url` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci,
  `city_id` int DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

--
-- Dumping data for table `master_spots`
--

INSERT INTO `master_spots` (`id`, `spot_name`, `image_url`, `city_id`) VALUES
(29, 'Amber Fort', 'Amber_Fort.jpeg', 1),
(30, 'Hawa Mahal', 'Hawa_Mahal.jpeg', 1),
(31, 'City Palace Jaipur', 'City_Palace_Jaipur.jpeg', 1),
(32, 'Jantar Mantar Jaipur', 'Jantar_Mantar_Jaipur.jpeg', 1),
(33, 'Nahargarh Fort', 'Nahargarh_Fort.jpeg', 1),
(34, 'Baga Beach', 'Baga_Beach.jpeg', 2),
(35, 'Calangute Beach', 'Calangute_Beach.jpeg', 2),
(36, 'Dudhsagar Waterfalls', 'Dashashwamedh_Ghat.jpeg', 2),
(37, 'Basilica of Bom Jesus', 'Basilica_of_Bom_Jesus.jpeg', 2),
(38, 'Fort Aguada', 'Fort_Aguada.jpeg', 2),
(39, 'Solang Valley', 'Solang_Valley.jpeg', 3),
(40, 'Rohtang Pass', 'Rohtang_Pass.jpeg', 3),
(41, 'Hadimba Temple', 'Hadimba_Temple.jpeg', 3),
(42, 'Vashisht Hot Springs', 'Vashisht_Hot_Springs.jpeg', 3),
(43, 'Old Manali', 'Old_Manali.jpeg', 3),
(44, 'City Palace Udaipur', 'City_Palace_Jaipur.jpeg', 4),
(45, 'Lake Pichola', 'Lake_Pichola.jpeg', 4),
(46, 'Jag Mandir', 'Jag_Mandir.jpeg', 4),
(47, 'Sajjangarh Monsoon Palace', 'Sajjangarh_Monsoon_Palace.jpeg', 4),
(48, 'Saheliyon Ki Bari', 'Saheliyon_Ki_Bari.jpeg', 4),
(49, 'Kashi Vishwanath Temple', 'Kashi_Vishwanath_Temple.jpeg', 5),
(50, 'Dashashwamedh Ghat', 'Dashashwamedh_Ghat.jpeg', 5),
(51, 'Assi Ghat', 'Assi_Ghat.jpeg', 5),
(52, 'Sarnath', 'Sarnath.jpeg', 5),
(53, 'Ramnagar Fort', 'Ramnagar_Fort.jpeg', 5),
(54, 'Ran Of Kuchh', 'rann-of-kutch-kutch-gujarat-1-attr-hero.jpeg', 6);

-- --------------------------------------------------------

--
-- Table structure for table `payments`
--

CREATE TABLE `payments` (
  `id` int NOT NULL,
  `booking_id` int NOT NULL,
  `amount` decimal(10,2) DEFAULT NULL,
  `paid` int DEFAULT '1'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

--
-- Dumping data for table `payments`
--

INSERT INTO `payments` (`id`, `booking_id`, `amount`, `paid`) VALUES
(8, 8, 30000.00, 1),
(10, 9, 56997.00, 1),
(11, 10, 15998.00, 1),
(12, 11, 10999.00, 1),
(13, 12, 37998.00, 1),
(14, 14, 13500.00, 1);

-- --------------------------------------------------------

--
-- Table structure for table `services`
--

CREATE TABLE `services` (
  `id` int NOT NULL,
  `provider_id` int DEFAULT NULL,
  `service_type` varchar(50) DEFAULT NULL,
  `service_name` varchar(100) DEFAULT NULL,
  `price` decimal(10,2) DEFAULT NULL,
  `description` text,
  `city_id` int DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

--
-- Dumping data for table `services`
--

INSERT INTO `services` (`id`, `provider_id`, `service_type`, `service_name`, `price`, `description`, `city_id`) VALUES
(1, 6, 'Hotel', 'Hotel Royal Stay', 2499.00, 'Comfortable stay near city center', 1);

-- --------------------------------------------------------

--
-- Table structure for table `service_bookings`
--

CREATE TABLE `service_bookings` (
  `id` int NOT NULL,
  `booking_id` int DEFAULT NULL,
  `service_id` int DEFAULT NULL,
  `status` enum('pending','accepted','rejected','completed') DEFAULT 'pending'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Table structure for table `states`
--

CREATE TABLE `states` (
  `id` int NOT NULL,
  `state_name` varchar(100) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

--
-- Dumping data for table `states`
--

INSERT INTO `states` (`id`, `state_name`) VALUES
(2, 'Goa'),
(10, 'Gujarat'),
(3, 'Himachal Pradesh'),
(1, 'Rajasthan'),
(4, 'Uttar Pradesh');

-- --------------------------------------------------------

--
-- Table structure for table `tours`
--

CREATE TABLE `tours` (
  `id` int NOT NULL,
  `title` varchar(255) NOT NULL,
  `description` text,
  `price` decimal(10,2) NOT NULL,
  `start_date` date DEFAULT NULL,
  `end_date` date DEFAULT NULL,
  `start_point` varchar(255) DEFAULT NULL,
  `end_point` varchar(255) DEFAULT NULL,
  `image_path` varchar(255) DEFAULT NULL,
  `travel_mode` varchar(40) DEFAULT NULL,
  `food_plan` varchar(60) DEFAULT NULL,
  `transport_details` varchar(255) DEFAULT NULL,
  `hotel_notes` text,
  `inclusions` text,
  `exclusions` text,
  `pickup_state_id` int DEFAULT NULL,
  `pickup_city_id` int DEFAULT NULL,
  `drop_state_id` int DEFAULT NULL,
  `drop_city_id` int DEFAULT NULL,
  `max_group_size` int DEFAULT NULL,
  `difficulty_level` varchar(30) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

--
-- Dumping data for table `tours`
--

INSERT INTO `tours` (`id`, `title`, `description`, `price`, `start_date`, `end_date`, `start_point`, `end_point`, `image_path`, `travel_mode`, `food_plan`, `transport_details`, `hotel_notes`, `inclusions`, `exclusions`, `pickup_state_id`, `pickup_city_id`, `drop_state_id`, `drop_city_id`, `max_group_size`, `difficulty_level`) VALUES
(11, 'Rajasthan', '3-days with hotel and food', 13500.00, '2026-02-17', '2026-02-20', 'Ahmedabad', 'Jaipur', 'City_Palace_Jaipur.jpeg', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
(12, 'Goa Beach & Adventure Escape', 'Enjoy a 5-day vacation in Goa covering North Goa beaches, South Goa heritage, water sports, cruise dinner and nightlife experiences. Perfect for friends and college groups.\r\n', 18999.00, '2026-03-09', '2026-03-14', 'Ahmedabad', 'Goa', 'back.jpg', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
(13, 'Manali Quick Escape', 'A short 3-day trip to Manaki covering Mall Road, Kufri snow point, Jakhoo Temple and scenic Himalayan viewpoints. Ideal for students and weekend travelers.\r\n', 7999.00, '2026-03-18', '2026-02-21', 'Delhi', 'Manali', 'Old_Manali.jpeg', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
(14, 'Spiritual Varanasi Experience', 'Experience the spiritual heart of India in Varanasi. Includes Ganga Aarti, Kashi Vishwanath Temple Darshan, Sarnath visit, morning boat ride and ancient ghats exploration.\r\n', 10999.00, '2026-04-01', '2026-02-04', 'Surat', 'Varanasi', 'Kashi_Vishwanath_Temple.jpeg', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);

-- --------------------------------------------------------

--
-- Table structure for table `tour_guide_links`
--

CREATE TABLE `tour_guide_links` (
  `id` int NOT NULL,
  `tour_id` int NOT NULL,
  `service_id` int NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Table structure for table `tour_hotel_links`
--

CREATE TABLE `tour_hotel_links` (
  `id` int NOT NULL,
  `tour_id` int NOT NULL,
  `service_id` int NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Table structure for table `tour_itinerary`
--

CREATE TABLE `tour_itinerary` (
  `id` int NOT NULL,
  `tour_id` int DEFAULT NULL,
  `spot_id` int DEFAULT NULL,
  `order_sequence` int DEFAULT NULL,
  `day_number` int DEFAULT '1'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

--
-- Dumping data for table `tour_itinerary`
--

INSERT INTO `tour_itinerary` (`id`, `tour_id`, `spot_id`, `order_sequence`, `day_number`) VALUES
(9, 11, 31, 0, 1),
(10, 11, 30, 1, 1),
(11, 11, 48, 2, 2),
(12, 11, 47, 3, 2),
(13, 12, 38, NULL, 1),
(14, 12, 37, NULL, 2),
(15, 12, 36, NULL, 3),
(16, 12, 35, NULL, 4),
(17, 12, 34, NULL, 5),
(18, 13, 43, NULL, 1),
(19, 13, 42, NULL, 1),
(20, 13, 41, NULL, 2),
(21, 13, 40, NULL, 3),
(22, 13, 39, NULL, 3),
(23, 14, 53, NULL, 1),
(24, 14, 52, NULL, 1),
(25, 14, 51, NULL, 2),
(26, 14, 50, NULL, 2),
(27, 14, 49, NULL, 2);

-- --------------------------------------------------------

--
-- Table structure for table `tour_services`
--

CREATE TABLE `tour_services` (
  `id` int NOT NULL,
  `tour_id` int DEFAULT NULL,
  `service_id` int DEFAULT NULL,
  `day_number` int DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Table structure for table `tour_transport_links`
--

CREATE TABLE `tour_transport_links` (
  `id` int NOT NULL,
  `tour_id` int NOT NULL,
  `service_id` int NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Table structure for table `transport_profiles`
--

CREATE TABLE `transport_profiles` (
  `id` int NOT NULL,
  `service_id` int NOT NULL,
  `transport_type` varchar(60) NOT NULL,
  `vehicle_model` varchar(120) DEFAULT NULL,
  `registration_number` varchar(50) DEFAULT NULL,
  `seating_capacity` int DEFAULT NULL,
  `luggage_capacity` varchar(80) DEFAULT NULL,
  `ac_available` tinyint(1) DEFAULT '1',
  `driver_available` tinyint(1) DEFAULT '1',
  `driver_name` varchar(120) DEFAULT NULL,
  `driver_phone` varchar(30) DEFAULT NULL,
  `price_per_day` decimal(10,2) DEFAULT NULL,
  `price_per_km` decimal(10,2) DEFAULT NULL,
  `permit_doc_path` varchar(255) DEFAULT NULL,
  `insurance_doc_path` varchar(255) DEFAULT NULL,
  `license_doc_path` varchar(255) DEFAULT NULL,
  `rc_doc_path` varchar(255) DEFAULT NULL,
  `notes` text,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Table structure for table `users`
--

CREATE TABLE `users` (
  `id` int NOT NULL,
  `password` varchar(255) NOT NULL,
  `full_name` varchar(100) NOT NULL,
  `email` varchar(120) NOT NULL,
  `phone` varchar(15) NOT NULL,
  `role` enum('admin','organizer','provider','customer') DEFAULT 'customer',
  `status` enum('pending','approved','rejected') DEFAULT 'approved',
  `document_path` varchar(255) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

--
-- Dumping data for table `users`
--

INSERT INTO `users` (`id`, `password`, `full_name`, `email`, `phone`, `role`, `status`, `document_path`) VALUES
(4, 'scrypt:32768:8:1$v0tC6LGlXmGvLPCI$170167800f29c61c2318f89bcb58c048428ef60e8f50da1e155008027fe90ccd7fb5d01d6a6d52d0498d97ea9078981df93d2f05556579360a92b95868a53e3b', 'Krish', '1savaliya5@gmail.com', '7990189577', 'admin', 'approved', NULL),
(5, 'scrypt:32768:8:1$v58ArpZhN5b6BWk2$6f693b4af48e2cd57fcae9b74b6ba3f704cc0cea5e8b9891d46bd5aa7557bc18a0594ae705046543bd6bc6bf9ab4d234ca4932599c7e39bedf5bdc9934041f7d', 'PATEL HEMIL', 'hemil513@gmail.com', '9712952405', 'customer', 'approved', NULL),
(6, 'scrypt:32768:8:1$9Gwc3rkh42mXoHbH$b244874c2fd772b594720b4a797ebc543b12477607740bf42e83cb080b6e9bc44ebb080bfc2410e436d1cd470ca39b901b8531e922db94adea8ccbcab41f08a5', 'PG', 'a@gmail.com', '9426168562', 'customer', 'approved', NULL),
(7, 'scrypt:32768:8:1$waVj3gWLBIK7p9S6$5065856c06c4c014e9e56d1080d9316547eb67f9e708286d3bf9a830f6e67669ec41afd20020c8f81321cded42c6c881117b0d45f6e9c7fc2dd88d0682b4c8f0', 'Ankitbhai', 'ankit@gmail.com', '9908390903', 'organizer', 'approved', '20260212223102101144_Screenshot_2026-02-02_at_7.14.54_PM.png'),
(8, 'scrypt:32768:8:1$gMEgg4qr2Y9BWFpA$ac765e9887e8e322302e93eb8860de0c28fc95f009b52261f6ec0e04b0b4fc934b4e0120c7e5a0aac7c2a08a6603cce8594b693b9abe5658374abaf7d0bd568f', 'prince', 'pm@gmail.com', '9245775429', 'provider', 'approved', '20260212224031588643_Screenshot_2026-02-01_at_2.25.55_PM.png');

-- --------------------------------------------------------

--
-- Table structure for table `user_approval_logs`
--

CREATE TABLE `user_approval_logs` (
  `id` int NOT NULL,
  `user_id` int NOT NULL,
  `admin_id` int NOT NULL,
  `action_taken` varchar(20) NOT NULL,
  `note` text,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Table structure for table `user_profiles`
--

CREATE TABLE `user_profiles` (
  `user_id` int NOT NULL,
  `requested_role` varchar(30) DEFAULT NULL,
  `business_name` varchar(120) DEFAULT NULL,
  `provider_category` varchar(60) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

--
-- Dumping data for table `user_profiles`
--

INSERT INTO `user_profiles` (`user_id`, `requested_role`, `business_name`, `provider_category`, `created_at`) VALUES
(7, 'organizer', 'Jay Ambe tours and travells', NULL, '2026-02-12 17:01:02'),
(8, 'provider', 'Sarovar Hotels', 'Hotel', '2026-02-12 17:10:31');

--
-- Indexes for dumped tables
--

--
-- Indexes for table `amenity_master`
--
ALTER TABLE `amenity_master`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `uk_amenity_name` (`amenity_name`);

--
-- Indexes for table `bookings`
--
ALTER TABLE `bookings`
  ADD PRIMARY KEY (`id`),
  ADD KEY `user_id` (`user_id`),
  ADD KEY `tour_id` (`tour_id`);

--
-- Indexes for table `booking_guide_requests`
--
ALTER TABLE `booking_guide_requests`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `uk_booking_guide_booking` (`booking_id`),
  ADD KEY `idx_booking_guide_service` (`service_id`);

--
-- Indexes for table `cities`
--
ALTER TABLE `cities`
  ADD PRIMARY KEY (`id`),
  ADD KEY `state_id` (`state_id`);

--
-- Indexes for table `hotel_amenities`
--
ALTER TABLE `hotel_amenities`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `uk_hotel_amenity` (`service_id`,`amenity_id`),
  ADD KEY `idx_hotel_amenity_service` (`service_id`),
  ADD KEY `idx_hotel_amenity_amenity` (`amenity_id`);

--
-- Indexes for table `hotel_bookings`
--
ALTER TABLE `hotel_bookings`
  ADD PRIMARY KEY (`id`),
  ADD KEY `idx_hotel_bookings_user` (`user_id`),
  ADD KEY `idx_hotel_bookings_service` (`service_id`),
  ADD KEY `idx_hotel_bookings_room_type` (`room_type_id`);

--
-- Indexes for table `hotel_images`
--
ALTER TABLE `hotel_images`
  ADD PRIMARY KEY (`id`),
  ADD KEY `idx_hotel_images_service` (`service_id`);

--
-- Indexes for table `hotel_profiles`
--
ALTER TABLE `hotel_profiles`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `uk_hotel_service` (`service_id`);

--
-- Indexes for table `hotel_reviews`
--
ALTER TABLE `hotel_reviews`
  ADD PRIMARY KEY (`id`),
  ADD KEY `idx_reviews_service` (`service_id`),
  ADD KEY `idx_reviews_user` (`user_id`);

--
-- Indexes for table `hotel_room_inventory_logs`
--
ALTER TABLE `hotel_room_inventory_logs`
  ADD PRIMARY KEY (`id`),
  ADD KEY `idx_inventory_room` (`room_type_id`),
  ADD KEY `idx_inventory_changed_by` (`changed_by`);

--
-- Indexes for table `hotel_room_types`
--
ALTER TABLE `hotel_room_types`
  ADD PRIMARY KEY (`id`),
  ADD KEY `idx_room_service` (`service_id`);

--
-- Indexes for table `master_spots`
--
ALTER TABLE `master_spots`
  ADD PRIMARY KEY (`id`),
  ADD KEY `fk_city` (`city_id`);

--
-- Indexes for table `payments`
--
ALTER TABLE `payments`
  ADD PRIMARY KEY (`id`),
  ADD KEY `booking_id` (`booking_id`);

--
-- Indexes for table `services`
--
ALTER TABLE `services`
  ADD PRIMARY KEY (`id`),
  ADD KEY `provider_id` (`provider_id`),
  ADD KEY `city_id` (`city_id`);

--
-- Indexes for table `service_bookings`
--
ALTER TABLE `service_bookings`
  ADD PRIMARY KEY (`id`),
  ADD KEY `booking_id` (`booking_id`),
  ADD KEY `service_id` (`service_id`);

--
-- Indexes for table `states`
--
ALTER TABLE `states`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `state_name` (`state_name`);

--
-- Indexes for table `tours`
--
ALTER TABLE `tours`
  ADD PRIMARY KEY (`id`);

--
-- Indexes for table `tour_guide_links`
--
ALTER TABLE `tour_guide_links`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `uk_tour_guide` (`tour_id`,`service_id`),
  ADD KEY `idx_tour_guide_tour` (`tour_id`),
  ADD KEY `idx_tour_guide_service` (`service_id`);

--
-- Indexes for table `tour_hotel_links`
--
ALTER TABLE `tour_hotel_links`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `uk_tour_hotel` (`tour_id`,`service_id`),
  ADD KEY `idx_tour_hotel_tour` (`tour_id`),
  ADD KEY `idx_tour_hotel_service` (`service_id`);

--
-- Indexes for table `tour_itinerary`
--
ALTER TABLE `tour_itinerary`
  ADD PRIMARY KEY (`id`),
  ADD KEY `tour_id` (`tour_id`),
  ADD KEY `spot_id` (`spot_id`);

--
-- Indexes for table `tour_services`
--
ALTER TABLE `tour_services`
  ADD PRIMARY KEY (`id`),
  ADD KEY `tour_id` (`tour_id`),
  ADD KEY `service_id` (`service_id`);

--
-- Indexes for table `tour_transport_links`
--
ALTER TABLE `tour_transport_links`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `uk_tour_transport` (`tour_id`,`service_id`),
  ADD KEY `idx_tour_transport_tour` (`tour_id`),
  ADD KEY `idx_tour_transport_service` (`service_id`);

--
-- Indexes for table `transport_profiles`
--
ALTER TABLE `transport_profiles`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `uk_transport_service` (`service_id`);

--
-- Indexes for table `users`
--
ALTER TABLE `users`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `email` (`email`),
  ADD UNIQUE KEY `phone` (`phone`);

--
-- Indexes for table `user_approval_logs`
--
ALTER TABLE `user_approval_logs`
  ADD PRIMARY KEY (`id`),
  ADD KEY `idx_user_approval_user` (`user_id`),
  ADD KEY `idx_user_approval_admin` (`admin_id`);

--
-- Indexes for table `user_profiles`
--
ALTER TABLE `user_profiles`
  ADD PRIMARY KEY (`user_id`);

--
-- AUTO_INCREMENT for dumped tables
--

--
-- AUTO_INCREMENT for table `amenity_master`
--
ALTER TABLE `amenity_master`
  MODIFY `id` int NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=401;

--
-- AUTO_INCREMENT for table `bookings`
--
ALTER TABLE `bookings`
  MODIFY `id` int NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=15;

--
-- AUTO_INCREMENT for table `booking_guide_requests`
--
ALTER TABLE `booking_guide_requests`
  MODIFY `id` int NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `cities`
--
ALTER TABLE `cities`
  MODIFY `id` int NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=7;

--
-- AUTO_INCREMENT for table `hotel_amenities`
--
ALTER TABLE `hotel_amenities`
  MODIFY `id` int NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=8;

--
-- AUTO_INCREMENT for table `hotel_bookings`
--
ALTER TABLE `hotel_bookings`
  MODIFY `id` int NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `hotel_images`
--
ALTER TABLE `hotel_images`
  MODIFY `id` int NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=15;

--
-- AUTO_INCREMENT for table `hotel_profiles`
--
ALTER TABLE `hotel_profiles`
  MODIFY `id` int NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=2;

--
-- AUTO_INCREMENT for table `hotel_reviews`
--
ALTER TABLE `hotel_reviews`
  MODIFY `id` int NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `hotel_room_inventory_logs`
--
ALTER TABLE `hotel_room_inventory_logs`
  MODIFY `id` int NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `hotel_room_types`
--
ALTER TABLE `hotel_room_types`
  MODIFY `id` int NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=4;

--
-- AUTO_INCREMENT for table `master_spots`
--
ALTER TABLE `master_spots`
  MODIFY `id` int NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=56;

--
-- AUTO_INCREMENT for table `payments`
--
ALTER TABLE `payments`
  MODIFY `id` int NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=15;

--
-- AUTO_INCREMENT for table `services`
--
ALTER TABLE `services`
  MODIFY `id` int NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=2;

--
-- AUTO_INCREMENT for table `service_bookings`
--
ALTER TABLE `service_bookings`
  MODIFY `id` int NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `states`
--
ALTER TABLE `states`
  MODIFY `id` int NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=11;

--
-- AUTO_INCREMENT for table `tours`
--
ALTER TABLE `tours`
  MODIFY `id` int NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=15;

--
-- AUTO_INCREMENT for table `tour_guide_links`
--
ALTER TABLE `tour_guide_links`
  MODIFY `id` int NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `tour_hotel_links`
--
ALTER TABLE `tour_hotel_links`
  MODIFY `id` int NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `tour_itinerary`
--
ALTER TABLE `tour_itinerary`
  MODIFY `id` int NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=28;

--
-- AUTO_INCREMENT for table `tour_services`
--
ALTER TABLE `tour_services`
  MODIFY `id` int NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `tour_transport_links`
--
ALTER TABLE `tour_transport_links`
  MODIFY `id` int NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `transport_profiles`
--
ALTER TABLE `transport_profiles`
  MODIFY `id` int NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `users`
--
ALTER TABLE `users`
  MODIFY `id` int NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=9;

--
-- AUTO_INCREMENT for table `user_approval_logs`
--
ALTER TABLE `user_approval_logs`
  MODIFY `id` int NOT NULL AUTO_INCREMENT;

--
-- Constraints for dumped tables
--

--
-- Constraints for table `bookings`
--
ALTER TABLE `bookings`
  ADD CONSTRAINT `bookings_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  ADD CONSTRAINT `bookings_ibfk_2` FOREIGN KEY (`tour_id`) REFERENCES `tours` (`id`) ON DELETE CASCADE;

--
-- Constraints for table `booking_guide_requests`
--
ALTER TABLE `booking_guide_requests`
  ADD CONSTRAINT `fk_booking_guide_booking` FOREIGN KEY (`booking_id`) REFERENCES `bookings` (`id`) ON DELETE CASCADE,
  ADD CONSTRAINT `fk_booking_guide_service` FOREIGN KEY (`service_id`) REFERENCES `services` (`id`) ON DELETE SET NULL;

--
-- Constraints for table `cities`
--
ALTER TABLE `cities`
  ADD CONSTRAINT `cities_ibfk_1` FOREIGN KEY (`state_id`) REFERENCES `states` (`id`) ON DELETE CASCADE;

--
-- Constraints for table `hotel_amenities`
--
ALTER TABLE `hotel_amenities`
  ADD CONSTRAINT `fk_hotel_amenities_master` FOREIGN KEY (`amenity_id`) REFERENCES `amenity_master` (`id`) ON DELETE CASCADE,
  ADD CONSTRAINT `fk_hotel_amenities_service` FOREIGN KEY (`service_id`) REFERENCES `services` (`id`) ON DELETE CASCADE;

--
-- Constraints for table `hotel_bookings`
--
ALTER TABLE `hotel_bookings`
  ADD CONSTRAINT `fk_hotel_bookings_room_type` FOREIGN KEY (`room_type_id`) REFERENCES `hotel_room_types` (`id`) ON DELETE CASCADE,
  ADD CONSTRAINT `fk_hotel_bookings_service` FOREIGN KEY (`service_id`) REFERENCES `services` (`id`) ON DELETE CASCADE,
  ADD CONSTRAINT `fk_hotel_bookings_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE;

--
-- Constraints for table `hotel_images`
--
ALTER TABLE `hotel_images`
  ADD CONSTRAINT `fk_hotel_images_service` FOREIGN KEY (`service_id`) REFERENCES `services` (`id`) ON DELETE CASCADE;

--
-- Constraints for table `hotel_profiles`
--
ALTER TABLE `hotel_profiles`
  ADD CONSTRAINT `fk_hotel_profiles_service` FOREIGN KEY (`service_id`) REFERENCES `services` (`id`) ON DELETE CASCADE;

--
-- Constraints for table `hotel_reviews`
--
ALTER TABLE `hotel_reviews`
  ADD CONSTRAINT `fk_reviews_service` FOREIGN KEY (`service_id`) REFERENCES `services` (`id`) ON DELETE CASCADE,
  ADD CONSTRAINT `fk_reviews_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE;

--
-- Constraints for table `hotel_room_inventory_logs`
--
ALTER TABLE `hotel_room_inventory_logs`
  ADD CONSTRAINT `fk_inventory_changed_by` FOREIGN KEY (`changed_by`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  ADD CONSTRAINT `fk_inventory_room_type` FOREIGN KEY (`room_type_id`) REFERENCES `hotel_room_types` (`id`) ON DELETE CASCADE;

--
-- Constraints for table `hotel_room_types`
--
ALTER TABLE `hotel_room_types`
  ADD CONSTRAINT `fk_room_types_service` FOREIGN KEY (`service_id`) REFERENCES `services` (`id`) ON DELETE CASCADE;

--
-- Constraints for table `master_spots`
--
ALTER TABLE `master_spots`
  ADD CONSTRAINT `fk_city` FOREIGN KEY (`city_id`) REFERENCES `cities` (`id`) ON DELETE CASCADE;

--
-- Constraints for table `payments`
--
ALTER TABLE `payments`
  ADD CONSTRAINT `payments_ibfk_1` FOREIGN KEY (`booking_id`) REFERENCES `bookings` (`id`) ON DELETE CASCADE;

--
-- Constraints for table `services`
--
ALTER TABLE `services`
  ADD CONSTRAINT `services_ibfk_1` FOREIGN KEY (`provider_id`) REFERENCES `users` (`id`),
  ADD CONSTRAINT `services_ibfk_2` FOREIGN KEY (`city_id`) REFERENCES `cities` (`id`);

--
-- Constraints for table `service_bookings`
--
ALTER TABLE `service_bookings`
  ADD CONSTRAINT `service_bookings_ibfk_1` FOREIGN KEY (`booking_id`) REFERENCES `bookings` (`id`),
  ADD CONSTRAINT `service_bookings_ibfk_2` FOREIGN KEY (`service_id`) REFERENCES `services` (`id`);

--
-- Constraints for table `tour_guide_links`
--
ALTER TABLE `tour_guide_links`
  ADD CONSTRAINT `fk_tour_guide_service` FOREIGN KEY (`service_id`) REFERENCES `services` (`id`) ON DELETE CASCADE,
  ADD CONSTRAINT `fk_tour_guide_tour` FOREIGN KEY (`tour_id`) REFERENCES `tours` (`id`) ON DELETE CASCADE;

--
-- Constraints for table `tour_hotel_links`
--
ALTER TABLE `tour_hotel_links`
  ADD CONSTRAINT `fk_tour_hotel_service` FOREIGN KEY (`service_id`) REFERENCES `services` (`id`) ON DELETE CASCADE,
  ADD CONSTRAINT `fk_tour_hotel_tour` FOREIGN KEY (`tour_id`) REFERENCES `tours` (`id`) ON DELETE CASCADE;

--
-- Constraints for table `tour_itinerary`
--
ALTER TABLE `tour_itinerary`
  ADD CONSTRAINT `tour_itinerary_ibfk_1` FOREIGN KEY (`tour_id`) REFERENCES `tours` (`id`) ON DELETE CASCADE,
  ADD CONSTRAINT `tour_itinerary_ibfk_2` FOREIGN KEY (`spot_id`) REFERENCES `master_spots` (`id`);

--
-- Constraints for table `tour_services`
--
ALTER TABLE `tour_services`
  ADD CONSTRAINT `tour_services_ibfk_1` FOREIGN KEY (`tour_id`) REFERENCES `tours` (`id`),
  ADD CONSTRAINT `tour_services_ibfk_2` FOREIGN KEY (`service_id`) REFERENCES `services` (`id`);

--
-- Constraints for table `tour_transport_links`
--
ALTER TABLE `tour_transport_links`
  ADD CONSTRAINT `fk_tour_transport_service` FOREIGN KEY (`service_id`) REFERENCES `services` (`id`) ON DELETE CASCADE,
  ADD CONSTRAINT `fk_tour_transport_tour` FOREIGN KEY (`tour_id`) REFERENCES `tours` (`id`) ON DELETE CASCADE;

--
-- Constraints for table `transport_profiles`
--
ALTER TABLE `transport_profiles`
  ADD CONSTRAINT `fk_transport_profiles_service` FOREIGN KEY (`service_id`) REFERENCES `services` (`id`) ON DELETE CASCADE;

--
-- Constraints for table `user_approval_logs`
--
ALTER TABLE `user_approval_logs`
  ADD CONSTRAINT `fk_user_approval_admin` FOREIGN KEY (`admin_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  ADD CONSTRAINT `fk_user_approval_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE;

--
-- Constraints for table `user_profiles`
--
ALTER TABLE `user_profiles`
  ADD CONSTRAINT `fk_user_profiles_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE;
COMMIT;

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
