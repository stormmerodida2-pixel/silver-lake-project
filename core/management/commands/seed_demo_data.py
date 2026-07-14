from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from drivers.models import Driver
from fleet.models import Vehicle, VehicleCategory
from reviews.models import Review

# The flyer's own fleet lineup (see brand_design memory) - real vehicle names, categories, and
# passenger counts SilverLake actually advertises, not invented placeholders. Uses get_or_create
# keyed on name so this is safe to re-run without duplicating vehicles each time.
VEHICLES = [
    {
        'name': 'Toyota Prado TZG', 'category_slug': 'executive_suv', 'passenger_capacity': 4,
        'tagline': 'Luxury, power, prestige', 'price_per_day': Decimal('18000'),
        'description': 'Our flagship executive SUV - leather interior, full-time 4WD, and the '
                        'presence to match any occasion, from airport transfers to weekend safaris.',
    },
    {
        'name': 'Toyota Voxy', 'category_slug': 'premium_mpv', 'passenger_capacity': 7,
        'tagline': 'Space and comfort for the whole family', 'price_per_day': Decimal('12000'),
        'description': 'A roomy, comfortable people-mover for family trips or small group travel '
                        'around Kisumu and beyond - sliding doors, generous legroom, smooth ride.',
    },
    {
        'name': 'Toyota Axio', 'category_slug': 'compact_sedan', 'passenger_capacity': 4,
        'tagline': 'Smart, efficient, always ready', 'price_per_day': Decimal('6000'),
        'description': 'Fuel-efficient and easy to drive - the practical choice for city errands, '
                        'client visits, or a self-drive weekend without the fuss.',
    },
    {
        'name': 'Toyota Hiace', 'category_slug': 'passenger_van', 'passenger_capacity': 13,
        'tagline': 'Built for groups, made for journeys', 'price_per_day': Decimal('15000'),
        'description': 'Our largest passenger van - ideal for group travel, church trips, or '
                        'ferrying a whole team between venues in comfort.',
    },
]

DRIVERS = [
    {
        'full_name': 'Emmanuel Otieno', 'years_of_experience': 8, 'rating': Decimal('4.90'),
        'bio': 'Been driving clients around Kisumu and beyond for eight years - knows every '
               'shortcut from the airport to the lakefront.',
    },
    {
        'full_name': 'Grace Achieng', 'years_of_experience': 5, 'rating': Decimal('4.80'),
        'bio': "Careful, punctual, and a favourite with SilverLake's returning corporate clients.",
    },
    {
        'full_name': 'Peter Mwangi', 'years_of_experience': 6, 'rating': Decimal('4.95'),
        'bio': 'Specialises in longer upcountry trips - Nairobi, Nakuru, and the western circuit.',
    },
]

REVIEWS = [
    {
        'customer_name': 'Wanjiru K.', 'rating': 5,
        'comment': 'Booked the Prado for a weekend at the lake - spotless car, driver was on time '
                   'and incredibly professional. Will book again.',
    },
    {
        'customer_name': 'Brian O.', 'rating': 5,
        'comment': "Used the Hiace for a church group trip to Kakamega. Comfortable, and the "
                   "driver handled a group of 12 without a single complaint.",
    },
    {
        'customer_name': 'Fatuma A.', 'rating': 4,
        'comment': 'Self-drive Axio was perfect for the week I was in Kisumu for work. Smooth '
                   'booking process, easy pickup.',
    },
    {
        'customer_name': 'David M.', 'rating': 5,
        'comment': "SilverLake has been our go-to for airport transfers for over a year now. "
                   "Always reliable, always on time.",
    },
    {
        'customer_name': 'Naomi W.', 'rating': 4,
        'comment': 'Great experience with the Voxy for a family trip - spacious and comfortable '
                   'for the kids. Only wish the booking app remembered my details for next time.',
    },
]


class Command(BaseCommand):
    help = (
        "Seeds demo-friendly vehicles, drivers, and approved reviews so the public site and "
        "admin dashboard don't look empty during a demo. Purely additive and safe to re-run - "
        "everything is keyed by name/customer_name via get_or_create, so it never duplicates or "
        "touches whatever real data already exists."
    )

    def handle(self, *args, **options):
        future_date = timezone.localdate().replace(year=timezone.localdate().year + 2)

        for data in VEHICLES:
            category = VehicleCategory.objects.get(slug=data['category_slug'])
            vehicle, created = Vehicle.objects.get_or_create(
                name=data['name'],
                defaults={
                    'category': category,
                    'passenger_capacity': data['passenger_capacity'],
                    'tagline': data['tagline'],
                    'price_per_day': data['price_per_day'],
                    'description': data['description'],
                    'is_available': True,
                    'allow_self_drive': True,
                    'allow_with_driver': True,
                    'insurance_expiry_date': future_date,
                    'inspection_expiry_date': future_date,
                },
            )
            self.stdout.write(f'{"Created" if created else "Already exists"}: vehicle "{vehicle.name}"')

        for data in DRIVERS:
            driver, created = Driver.objects.get_or_create(
                full_name=data['full_name'],
                defaults={
                    'years_of_experience': data['years_of_experience'],
                    'rating': data['rating'],
                    'bio': data['bio'],
                    'is_active': True,
                },
            )
            self.stdout.write(f'{"Created" if created else "Already exists"}: driver "{driver.full_name}"')

        for data in REVIEWS:
            review, created = Review.objects.get_or_create(
                customer_name=data['customer_name'],
                comment=data['comment'],
                defaults={'rating': data['rating'], 'is_approved': True},
            )
            self.stdout.write(f'{"Created" if created else "Already exists"}: review from "{review.customer_name}"')

        self.stdout.write(self.style.SUCCESS('Demo data seeded.'))
