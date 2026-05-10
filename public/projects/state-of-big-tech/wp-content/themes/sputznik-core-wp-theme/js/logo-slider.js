
jQuery(document).ready(function(){


	jQuery('[data-behaviour~=logos-slick]').each( function(){

		var $el = jQuery( this );

		$el.slick({
			slidesToShow	: $el.data('items'),
			slidesToScroll	: 1,
			autoplay		: true,
			autoplaySpeed	: 1500,
			arrows			: false,
			dots			: false,
			pauseOnHover	: false,
			responsive		: [{
				breakpoint	: 960,
				settings	: { slidesToShow: 4 }
			}, {
				breakpoint: 768,
				settings: { slidesToShow: 3 }
			},{
        breakpoint: 520,
				settings: { slidesToShow: 2 }
      }]
		});

	});

});
