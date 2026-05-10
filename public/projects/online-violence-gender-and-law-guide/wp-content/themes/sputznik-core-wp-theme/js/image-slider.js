
jQuery(document).ready(function(){


	jQuery('[data-behaviour~=images-slick]').each( function(){

		var $el = jQuery( this );

		$el.slick({
			slidesToShow		: $el.data('items'),
			slidesToScroll	: 1,
			autoplay				: true,
			autoplaySpeed		: 1500,
			arrows					: true,
			dots						: true,
			pauseOnHover		: true,
			responsive			: [
				{
					breakpoint	: 1300,
					settings	: { slidesToShow: 3}
				},
				{
					breakpoint: 769,
					settings: {slidesToShow: 2}
				},
				{
	        breakpoint: 520,
					settings: { slidesToShow: 1 }
      }
		]
		});

	});
	jQuery("[data-behaviour~=images-slick].slider").slick("refresh");

});
