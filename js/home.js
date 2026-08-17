(function () {
    var carousels = document.querySelectorAll('[data-home-carousel]');

    Array.prototype.forEach.call(carousels, function (carousel) {
        var track = carousel.querySelector('[data-carousel-track]');
        var previous = carousel.querySelector('[data-carousel-previous]');
        var next = carousel.querySelector('[data-carousel-next]');

        function scrollDistance() {
            var card = track.querySelector('[data-carousel-card]');
            if (!card) return track.clientWidth;
            var styles = window.getComputedStyle(track);
            var gap = parseFloat(styles.columnGap || styles.gap) || 0;
            return card.getBoundingClientRect().width + gap;
        }

        function updateButtons() {
            var maximum = track.scrollWidth - track.clientWidth;
            previous.disabled = track.scrollLeft <= 2;
            next.disabled = track.scrollLeft >= maximum - 2;
        }

        previous.addEventListener('click', function () {
            track.scrollBy({ left: -scrollDistance(), behavior: 'smooth' });
        });

        next.addEventListener('click', function () {
            track.scrollBy({ left: scrollDistance(), behavior: 'smooth' });
        });

        track.addEventListener('scroll', updateButtons);
        window.addEventListener('resize', updateButtons);
        updateButtons();
    });
}());
