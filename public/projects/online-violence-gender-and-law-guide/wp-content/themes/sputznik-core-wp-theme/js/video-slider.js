jQuery(document).ready(function(){

  /* RELATED POSTS SLIDER */
	jQuery('[data-behaviour~=sp-video-slider]').each( function () {
		var $this = jQuery( this ),
			slide = $this.data('items');
			$this.slick({
				infinite      : true,
				slidesToShow  : slide,
				slidesToScroll: 1,
				dots          : true,
				autoplay      : false,
				autoplaySpeed : 5000,
				speed         : 300,
				arrows        : true,
				nextArrow     : '<button type="button" class="slick-next slick-nav"><i class="fa fa-angle-right"></i></button>',
				prevArrow     : '<button type="button" class="slick-prev slick-nav"><i class="fa fa-angle-left"></i></button>',
				responsive    : [
					{
						breakpoint: 1169,
						settings  : {
							slidesToShow  : 2,
							slidesToScroll: 2
						}
					},
					{
						breakpoint: 769,
						settings  : {
							slidesToShow  : 1,
							slidesToScroll: 1
						}
					}
				]
			});	// slick

			$this.addClass( 'loaded' );
	});

	jQuery('[data-behaviour~=sp-video-slider]').each( function () {

		var $el = jQuery( this ),
				$img = $el.find('.play-btn img');
				$img_url = $el.parent().data('play_btn_img');

		// Update play button image url
		if($img_url.length > 0){
			$img.attr('src', $img_url );
		}

	});


});
