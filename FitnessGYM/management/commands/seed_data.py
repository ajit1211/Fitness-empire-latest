"""Populate every table with realistic demo data.

    python manage.py seed_data            # fill anything that is missing
    python manage.py seed_data --flush    # wipe the demo rows first, then fill

The command is idempotent: running it twice does not create duplicates, because
every record is looked up by a natural key before it is created.
"""

import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from FitnessGYM.models import (
    Category,
    Customer,
    Equipment,
    FitnessClass,
    FitnessProgram,
    GymMembership,
    Membership,
    Membershipmonth,
    Orders,
    Product,
    Supplement,
    SupplementCategory,
    Trainer,
    UserProfile,
    aboutus,
    cart,
    membershipprocessedtocheck,
    processedtocheck,
)

CAT = "catalog/"


# ---------------------------------------------------------------------------
# Source data
# ---------------------------------------------------------------------------
SUPPLEMENT_CATEGORIES = [
    ("Whey Protein", "Fast-absorbing protein powders for post-workout recovery."),
    ("Mass Gainers", "High-calorie blends for athletes who struggle to add size."),
    ("Creatine", "Clinically dosed creatine for strength and power output."),
    ("Vitamins", "Daily micronutrient support for training and immunity."),
    ("Pre-Workout", "Energy, focus and pump formulas for hard sessions."),
    ("Accessories", "Shakers, belts, straps and everything else in your gym bag."),
]

SUPPLEMENTS = [
    # (name, category, price, rating, stock, image, description)
    ("Empire Whey Isolate 2kg", "Whey Protein", 4499, 4.8, 42, "whey.webp",
     "27g of fast-digesting isolate protein per scoop with under 1g of sugar. "
     "Mixes clean in water and sits light on the stomach."),
    ("Gold Standard Whey 1kg", "Whey Protein", 3299, 4.7, 30, "gold.webp",
     "A classic blend of whey isolate and concentrate. Twenty-four grams of "
     "protein per serving to support daily recovery."),
    ("Hydro ISO Zero 900g", "Whey Protein", 3899, 4.6, 18, "iso.webp",
     "Hydrolysed isolate with zero added sugar, built for cutting phases and "
     "lactose-sensitive lifters."),
    ("Serious Mass Gainer 3kg", "Mass Gainers", 3999, 4.5, 24, "mass_gainer.webp",
     "1,250 calories per serving with a 3:1 carb to protein ratio. For hard "
     "gainers who need help hitting a surplus."),
    ("Bulk Fuel Gainer 5kg", "Mass Gainers", 5499, 4.4, 12, "pribito.webp",
     "Slow and fast carbohydrates with added MCTs. Designed for a sustained "
     "off-season bulk rather than a quick spike."),
    ("Micronised Creatine 300g", "Creatine", 1299, 4.9, 60, "cretain.webp",
     "Pure micronised creatine monohydrate, 5g per serving. The most "
     "researched strength supplement there is."),
    ("Creatine HCL Capsules", "Creatine", 1599, 4.5, 35, "asulotion.webp",
     "Concentrated creatine hydrochloride in capsule form. No loading phase "
     "and no water retention."),
    ("Daily Multivitamin 90 Tabs", "Vitamins", 899, 4.6, 75, "multivitimine.webp",
     "Twenty-three vitamins and minerals in a single daily tablet, dosed for "
     "people who train four or more times a week."),
    ("Omega-3 Fish Oil 120 Caps", "Vitamins", 1099, 4.7, 48, "omega.webp",
     "Triple-strength EPA and DHA for joint comfort and heart health. "
     "Molecularly distilled and free of any fishy aftertaste."),
    ("Plant Protein Vegan 1kg", "Vitamins", 2899, 4.3, 22, "vegan.webp",
     "Pea and brown rice protein with a complete amino acid profile. Dairy "
     "free, soy free and naturally sweetened."),
    ("Nitro Pre-Workout 400g", "Pre-Workout", 2199, 4.6, 28, "shake1.webp",
     "Citrulline, beta-alanine and 200mg of caffeine for clean energy without "
     "the crash afterwards."),
    ("Pump Matrix Caffeine-Free", "Pre-Workout", 1999, 4.2, 20, "shake2.webp",
     "Stimulant-free pump formula for late-evening sessions when caffeine "
     "would wreck your sleep."),
    ("BCAA Recovery 450g", "Pre-Workout", 1799, 4.4, 33, "shake3.webp",
     "A 2:1:1 ratio of branched-chain amino acids with added electrolytes for "
     "long training sessions."),
    ("Empire Steel Shaker 700ml", "Accessories", 799, 4.8, 90, "bottle_gym.webp",
     "Insulated stainless steel shaker with a leak-proof lid. Keeps a cold "
     "drink cold for twelve hours."),
    ("Lifting Gloves Pro", "Accessories", 1199, 4.5, 55, "gloves.webp",
     "Padded palm with a breathable mesh back and a wrist wrap for heavy "
     "pressing and pulling."),
    ("Resistance Band Set", "Accessories", 1499, 4.6, 40, "band1.webp",
     "Five graded latex bands from light to extra heavy, with door anchor and "
     "carry bag included."),
    ("Yoga & Stretch Mat 6mm", "Accessories", 1699, 4.7, 26, "mat.webp",
     "Non-slip six millimetre mat with alignment markings. Comfortable for "
     "floor work and stable enough for balance poses."),
    ("Adjustable Dumbbell 20kg", "Accessories", 6499, 4.9, 8, "dumbles.webp",
     "One pair replaces a full rack. Twist the handle to change load from "
     "2.5kg to 20kg per hand."),
    ("Microfibre Gym Towel", "Accessories", 499, 4.3, 120, "gym_towel.webp",
     "Quick-drying microfibre towel with a hook loop so it stays on the bar "
     "instead of the floor."),
    ("Training Duffel Bag 45L", "Accessories", 2499, 4.5, 16, "gymbag.webp",
     "Separate ventilated shoe compartment, wet pocket and a padded strap. "
     "Fits a full change of kit plus shoes."),
]

CLASS_CATEGORIES = ["Cardio", "Strength", "Mind & Body", "Cycle"]

# Six classes per category: every category clears the 5-minimum with room to
# grow towards the 10-maximum, and 24 tiles divide evenly at 4, 3, 2 and 1 wide.
CLASSES = [
    # Cardio
    ("HIIT Core Burn", "Cardio", "hiit_core.webp"),
    ("Cardio Circuit", "Cardio", "cardio.webp"),
    ("Cardio HIIT Express", "Cardio", "cardiohiit.webp"),
    ("Step Athletic", "Cardio", "step_icon.webp"),
    ("Run Club", "Cardio", "become_a.webp"),
    ("Bootcamp Blast", "Cardio", "asulotion.webp"),
    # Strength
    ("Strength & Sweat", "Strength", "strength_sweat_icon.webp"),
    ("Strength HIIT", "Strength", "strength_hiit_icon.webp"),
    ("Muscle Pump", "Strength", "muscle_pump_icon.webp"),
    ("Olympic Lift Lab", "Strength", "lift_icon.webp"),
    ("Barbell Club", "Strength", "muscle3.webp"),
    ("Dumbbell Power", "Strength", "dumbles.webp"),
    # Mind & Body
    ("Hatha Yoga", "Mind & Body", "hatha_yoga_icon.webp"),
    ("Barre Sculpt", "Mind & Body", "barre.webp"),
    ("Master Mobility", "Mind & Body", "master_mobility_icon.webp"),
    ("Mat Pilates", "Mind & Body", "mat.webp"),
    ("Band Mobility", "Mind & Body", "streatch_band.webp"),
    ("Restorative Stretch", "Mind & Body", "thank.webp"),
    # Cycle
    ("Tru-Ride Cycling", "Cycle", "cycling_icon.webp"),
    ("Full Throttle Ride", "Cycle", "full_throttle_icon.webp"),
    ("Rhythm Circuit", "Cycle", "circuit.webp"),
    ("Sprint Intervals", "Cycle", "healthy2.webp"),
    ("Endurance Ride", "Cycle", "trsiner.webp"),
    ("Power Climb", "Cycle", "trainer.webp"),
]

ANNUAL_PLANS = [
    ("CORE", 24900, "Single club access, full gym floor, locker rooms and the "
                    "Fitness Empire app. The essentials, done properly."),
    ("PREMIER", 34900, "Multi-club access plus unlimited group fitness classes, "
                       "Tru-Ride cycling and one body scan every month."),
    ("EXECUTIVE", 44900, "Everything in Premier with towel service, guest passes, "
                         "sauna and steam access and priority class booking."),
]

MONTHLY_PLANS = [
    ("CORE", 2400, "Single club access with no lock-in. Cancel any month."),
    ("PREMIER", 3200, "Multi-club access and unlimited group classes, billed monthly."),
    ("EXECUTIVE", 4100, "The full club experience with towel service and guest passes."),
]

GYM_MEMBERSHIPS = [
    (1, "Day Pass", 399, 1, "Single-day access to the gym floor and locker rooms."),
    (2, "Weekly Trial", 999, 7, "Seven consecutive days of full access for new members."),
    (3, "Quarterly Core", 6900, 90, "Three months of single-club access."),
    (4, "Half-Yearly Premier", 18900, 180, "Six months of multi-club access with classes."),
    (5, "Annual Executive", 44900, 365, "Twelve months with every premium amenity included."),
]

PROGRAMS = [
    (1, "Beginner Foundations", 6, "Beginner",
     "A six-week introduction to resistance training. Learn the squat, hinge, "
     "press and pull with a coach checking every session."),
    (2, "Fat Loss Accelerator", 8, "Intermediate",
     "Eight weeks of metabolic conditioning paired with a structured nutrition "
     "plan and weekly body composition checks."),
    (3, "Strength Builder 5x5", 12, "Intermediate",
     "Twelve weeks of linear progression on the main compound lifts with "
     "accessory work to keep the joints healthy."),
    (4, "Athlete Power Camp", 10, "Advanced",
     "Olympic lifting, plyometrics and sprint mechanics for competitive "
     "athletes in the off-season."),
    (5, "Mobility & Rehab", 6, "Beginner",
     "Restore range of motion after injury or desk work with guided mobility "
     "flows and soft-tissue work."),
    (6, "Contest Prep Elite", 16, "Advanced",
     "Sixteen weeks of periodised training, peak-week planning and stage "
     "presentation coaching."),
]

TRAINERS = [
    (1, "Arjun Mehta", "Strength & Conditioning", 9, "arjun.mehta@fitnessempire.in"),
    (2, "Priya Nair", "Yoga & Mobility", 7, "priya.nair@fitnessempire.in"),
    (3, "Rahul Verma", "Olympic Weightlifting", 11, "rahul.verma@fitnessempire.in"),
    (4, "Sneha Kulkarni", "Sports Nutrition", 6, "sneha.kulkarni@fitnessempire.in"),
    (5, "Vikram Singh", "Functional Training", 8, "vikram.singh@fitnessempire.in"),
    (6, "Ananya Das", "Group Fitness & Cycle", 5, "ananya.das@fitnessempire.in"),
    (7, "Karthik Iyer", "Powerlifting", 12, "karthik.iyer@fitnessempire.in"),
    (8, "Meera Joshi", "Pre/Post Natal Fitness", 6, "meera.joshi@fitnessempire.in"),
]

EQUIPMENT = [
    (1, "Rogue Power Rack R-6", "Strength", "Excellent", 185000),
    (2, "Olympic Barbell 20kg", "Strength", "Excellent", 24000),
    (3, "Adjustable Bench Pro", "Strength", "Good", 32000),
    (4, "Technogym Treadmill Run", "Cardio", "Excellent", 425000),
    (5, "Concept2 RowErg", "Cardio", "Excellent", 145000),
    (6, "Assault AirBike Classic", "Cardio", "Good", 98000),
    (7, "Tru-Ride Spin Bike", "Cycle", "Excellent", 76000),
    (8, "Cable Crossover Station", "Strength", "Good", 168000),
    (9, "Hex Dumbbell Set 2-50kg", "Strength", "Excellent", 210000),
    (10, "Competition Kettlebell Set", "Functional", "Good", 64000),
    (11, "Plyometric Box Set", "Functional", "Fair", 18000),
    (12, "Infrared Sauna Cabin", "Recovery", "Excellent", 340000),
]

PRODUCTS = [
    (101, "Empire Training Tee", 1299, "catalog/member.webp",
     "Breathable moisture-wicking training tee with the Empire crest on the chest."),
    (102, "Performance Shorts 7in", 1599, "catalog/trainner.webp",
     "Four-way stretch shorts with a zip pocket and a no-ride liner."),
    (103, "Lifting Belt 10mm", 2999, "catalog/gloves1.webp",
     "Ten millimetre leather belt with a double-prong buckle for heavy squats."),
    (104, "Wrist Wraps Heavy", 899, "catalog/gloves.webp",
     "Stiff eighteen-inch wraps for pressing days and overhead work."),
    (105, "Knee Sleeves 7mm Pair", 2499, "catalog/weight1.webp",
     "Seven millimetre neoprene sleeves that add warmth and support under load."),
    (106, "Empire Water Bottle 1L", 699, "catalog/bottle1.webp",
     "One litre tritan bottle with time markers so you actually finish it."),
]

DEMO_USERS = [
    ("rohan", "Rohan Sharma", "rohan.sharma@example.com", "Male", "9820011223"),
    ("neha", "Neha Gupta", "neha.gupta@example.com", "Female", "9820044556"),
    ("imran", "Imran Qureshi", "imran.qureshi@example.com", "Male", "9820077889"),
    ("divya", "Divya Menon", "divya.menon@example.com", "Female", "9820033441"),
    ("sameer", "Sameer Patil", "sameer.patil@example.com", "Male", "9820066778"),
]

FEEDBACK = [
    ("Rohan Sharma", "rohan.sharma@example.com",
     "Joined three months ago and the Kick Starter sessions were worth it on their own."),
    ("Neha Gupta", "neha.gupta@example.com",
     "Could you add a couple more evening yoga slots? The 7pm class fills up instantly."),
    ("Imran Qureshi", "imran.qureshi@example.com",
     "Ordered the whey isolate on Tuesday and it arrived Thursday. No complaints at all."),
    ("Divya Menon", "divya.menon@example.com",
     "The mobility program fixed shoulder pain I had been carrying for two years."),
    ("Sameer Patil", "sameer.patil@example.com",
     "Is there a student discount on the annual Premier plan? Happy to show ID."),
]

CITIES = [
    ("Mumbai", "400001", "Maharashtra"),
    ("Pune", "411001", "Maharashtra"),
    ("Bengaluru", "560001", "Karnataka"),
    ("Hyderabad", "500001", "Telangana"),
    ("Delhi", "110001", "Delhi"),
]


class Command(BaseCommand):
    help = "Populate every table with realistic demo data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Delete existing demo rows before seeding.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        random.seed(20260922)

        if options["flush"]:
            self.stdout.write("Flushing existing demo data...")
            for model in (
                Orders, cart, processedtocheck, membershipprocessedtocheck,
                Supplement, SupplementCategory, FitnessClass, Category,
                Membership, Membershipmonth, GymMembership, FitnessProgram,
                Trainer, Equipment, Product, Customer, aboutus,
            ):
                model.objects.all().delete()
            User.objects.filter(is_superuser=False).delete()

        counts = {}

        # ------------------------------------------------------------------
        # Users
        # ------------------------------------------------------------------
        admin, created = User.objects.get_or_create(
            username="ajit",
            defaults={
                "email": "owner@shubhamtanks.com",
                "first_name": "Ajit",
                "last_name": "Pandey",
                "is_staff": True,
                "is_superuser": True,
            },
        )
        admin.is_staff = True
        admin.is_superuser = True
        admin.set_password("1")
        admin.save()
        UserProfile.objects.update_or_create(
            user=admin,
            defaults={
                "full_name": "Ajit Pandey",
                "gender": "Male",
                "phone": "9819978432",
                "email": admin.email,
            },
        )
        counts["superuser"] = "ajit"

        members = []
        for username, full_name, email, gender, phone in DEMO_USERS:
            user, was_new = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": email,
                    "first_name": full_name.split()[0],
                    "last_name": full_name.split()[-1],
                },
            )
            if was_new:
                user.set_password("empire@123")
                user.save()
            UserProfile.objects.update_or_create(
                user=user,
                defaults={
                    "full_name": full_name,
                    "gender": gender,
                    "phone": phone,
                    "email": email,
                },
            )
            members.append(user)
        counts["users"] = User.objects.count()
        counts["user profiles"] = UserProfile.objects.count()

        # ------------------------------------------------------------------
        # Catalogue
        # ------------------------------------------------------------------
        cats = {}
        for name, desc in SUPPLEMENT_CATEGORIES:
            obj, _ = SupplementCategory.objects.get_or_create(
                categoryName=name, defaults={"categoryDescription": desc}
            )
            cats[name] = obj
        counts["supplement categories"] = SupplementCategory.objects.count()

        supplements = []
        for name, cat, price, rating, stock, image, desc in SUPPLEMENTS:
            obj, _ = Supplement.objects.get_or_create(
                supplementName=name,
                defaults={
                    "supplementDescription": desc,
                    "supplementPrice": Decimal(price),
                    "supplementImage": CAT + image,
                    "supplementRating": Decimal(str(rating)),
                    "supplementCategory": cats[cat],
                    "stock": stock,
                    "is_deleted": False,
                },
            )
            supplements.append(obj)
        counts["supplements"] = Supplement.objects.count()

        # ------------------------------------------------------------------
        # Classes
        # ------------------------------------------------------------------
        class_cats = {}
        for name in CLASS_CATEGORIES:
            obj, _ = Category.objects.get_or_create(name=name)
            class_cats[name] = obj
        counts["class categories"] = Category.objects.count()

        for name, cat, image in CLASSES:
            FitnessClass.objects.get_or_create(
                name=name,
                defaults={"category": class_cats[cat], "image": CAT + image},
            )
        counts["fitness classes"] = FitnessClass.objects.count()

        # ------------------------------------------------------------------
        # Plans
        # ------------------------------------------------------------------
        annual = []
        for name, price, desc in ANNUAL_PLANS:
            obj, _ = Membership.objects.get_or_create(
                name=name,
                defaults={
                    "choice": "Annual",
                    "price": Decimal(price),
                    "description": desc,
                },
            )
            annual.append(obj)
        counts["annual plans"] = Membership.objects.count()

        monthly = []
        for name, price, desc in MONTHLY_PLANS:
            obj, _ = Membershipmonth.objects.get_or_create(
                name=name,
                defaults={
                    "choice": "Monthly",
                    "price": Decimal(price),
                    "description": desc,
                },
            )
            monthly.append(obj)
        counts["monthly plans"] = Membershipmonth.objects.count()

        gym_plans = []
        for mid, name, price, duration, desc in GYM_MEMBERSHIPS:
            obj, _ = GymMembership.objects.get_or_create(
                membershipId=mid,
                defaults={
                    "membershipName": name,
                    "membershipPrice": Decimal(price),
                    "duration": duration,
                    "description": desc,
                },
            )
            gym_plans.append(obj)
        counts["gym memberships"] = GymMembership.objects.count()

        # ------------------------------------------------------------------
        # Programs, trainers, equipment, merchandise
        # ------------------------------------------------------------------
        for pid, name, weeks, level, desc in PROGRAMS:
            FitnessProgram.objects.get_or_create(
                programId=pid,
                defaults={
                    "programName": name,
                    "programDurations": weeks,
                    "programLevel": level,
                    "programDescription": desc,
                },
            )
        counts["fitness programs"] = FitnessProgram.objects.count()

        for tid, name, spec, years, email in TRAINERS:
            Trainer.objects.get_or_create(
                trainerId=tid,
                defaults={
                    "trainerName": name,
                    "trainerSpecialization": spec,
                    "trainerExperience": years,
                    "trainerEmail": email,
                },
            )
        counts["trainers"] = Trainer.objects.count()

        for eid, name, etype, condition, price in EQUIPMENT:
            Equipment.objects.get_or_create(
                equipmentId=eid,
                defaults={
                    "equipmentName": name,
                    "equipmentType": etype,
                    "equipmentCondition": condition,
                    "equipmentPrice": Decimal(price),
                },
            )
        counts["equipment"] = Equipment.objects.count()

        for pid, name, price, image, desc in PRODUCTS:
            Product.objects.get_or_create(
                productId=pid,
                defaults={
                    "productName": name,
                    "productPrice": Decimal(price),
                    "productDescription": desc,
                    "productImage": image,
                },
            )
        counts["products"] = Product.objects.count()

        # ------------------------------------------------------------------
        # Customers (legacy CRM table + REST API demo)
        # ------------------------------------------------------------------
        for i, (username, full_name, email, _gender, phone) in enumerate(DEMO_USERS):
            Customer.objects.get_or_create(
                customerEmail=email,
                defaults={
                    "customerName": full_name,
                    "customerPhone": phone,
                    "membership": gym_plans[i % len(gym_plans)],
                },
            )
        counts["customers"] = Customer.objects.count()

        # ------------------------------------------------------------------
        # Shipping addresses
        # ------------------------------------------------------------------
        for i, user in enumerate(members):
            city, pin, state = CITIES[i % len(CITIES)]
            profile = UserProfile.objects.filter(user=user).first()
            processedtocheck.objects.get_or_create(
                user=user,
                defaults={
                    "full_name": profile.full_name,
                    "email": profile.email,
                    "phone_number": profile.phone,
                    "address": f"{12 + i} Fitness Lane, Sector {3 + i}",
                    "city": city,
                    "pin_code": pin,
                    "country": "India",
                    "additional_notes": "Please call before delivery." if i % 2 else "",
                },
            )
        counts["shipping addresses"] = processedtocheck.objects.count()

        # ------------------------------------------------------------------
        # Memberships bought by members
        # ------------------------------------------------------------------
        now = timezone.now()
        for i, user in enumerate(members):
            city, pin, _state = CITIES[i % len(CITIES)]
            profile = UserProfile.objects.filter(user=user).first()
            yearly = annual[i % len(annual)] if i % 2 == 0 else None
            month = monthly[i % len(monthly)] if i % 2 == 1 else None
            paid = i < 4  # the last member is left mid-payment on purpose

            membershipprocessedtocheck.objects.get_or_create(
                user=user,
                defaults={
                    "membership_yearly": yearly,
                    "membership_monthly": month,
                    "payment_status": paid,
                    "full_name": profile.full_name,
                    "email": profile.email,
                    "phone_number": profile.phone,
                    "city": city,
                    "pin_code": pin,
                    "plan_expiry": now + timedelta(days=365 if yearly else 30),
                },
            )
        counts["memberships sold"] = membershipprocessedtocheck.objects.count()

        # ------------------------------------------------------------------
        # Live carts
        # ------------------------------------------------------------------
        for user in members[:3]:
            for product in random.sample(supplements, 2):
                cart.objects.get_or_create(
                    userid=user,
                    productid=product,
                    defaults={"quantity": random.randint(1, 3)},
                )
        counts["cart rows"] = cart.objects.count()

        # ------------------------------------------------------------------
        # Order history across every status
        # ------------------------------------------------------------------
        statuses = ["PENDING", "PROCESSING", "SHIPPED", "DELIVERED", "CANCELLED"]
        if not Orders.objects.exists():
            created_orders = 0
            for i, user in enumerate(members):
                for j in range(3):
                    product = supplements[(i * 3 + j) % len(supplements)]
                    qty = random.randint(1, 3)
                    order = Orders.objects.create(
                        customer=user,
                        supplement=product,
                        quantity=qty,
                        status=statuses[(i + j) % len(statuses)],
                        total_price=product.supplementPrice * qty,
                    )
                    # Spread orders back over the last six weeks.
                    Orders.objects.filter(pk=order.pk).update(
                        order_date=now - timedelta(days=3 * (i * 3 + j) + 1)
                    )
                    created_orders += 1
        counts["orders"] = Orders.objects.count()

        # ------------------------------------------------------------------
        # Contact form messages
        # ------------------------------------------------------------------
        for name, email, message in FEEDBACK:
            aboutus.objects.get_or_create(
                email=email, message=message, defaults={"name": name}
            )
        counts["contact messages"] = aboutus.objects.count()

        # ------------------------------------------------------------------
        # Report
        # ------------------------------------------------------------------
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Demo data ready."))
        width = max(len(k) for k in counts)
        for key, value in counts.items():
            self.stdout.write(f"  {key.ljust(width)}  {value}")
        self.stdout.write("")
        self.stdout.write("  Admin login    ajit / 1")
        self.stdout.write("  Member logins  rohan, neha, imran, divya, sameer / empire@123")
