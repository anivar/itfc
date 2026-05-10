jQuery.fn.smooth_scroll = function( options ) {

	return this.each(function() {

		var $el = jQuery(this);

		// CHECK IF TARGET EXISTS WITHIN THE BODY
		$el.isTargetValid = function(){

			var $target = $el.getTarget();

			if( $target.length && !$target.is( ':hidden' ) ) {
				return true;
			}

			return false;

		};

		// PARSE URL - HELPER FUNCTION
		$el.parseURL = function( url ){
			var a = document.createElement('a');
			a.href = url;
			return a;
		};

		// RETURN TARGET ELEMENT
		$el.getTarget = function(){
			var hash = $el.parseURL( $el.attr( 'href' ) ).hash;
			return jQuery('body').find( hash );
		};


		$el.on( 'click', function( event ) {

			//removes smooth scroll if data-toggle=modal
			if ( !( jQuery(this).attr('data-toggle') == 'modal' ) ) {

				if( $el.isTargetValid() ){

					event.preventDefault();
					jQuery('.modal').modal('hide');

					jQuery('html, body').stop().animate({
						scrollTop: $el.getTarget().offset().top
					}, 1000);

				}

			}

		});

	});
};




jQuery(document).ready(function () {

	jQuery('a[href]').smooth_scroll();


});


/****Header3 Scroll Toggle****/
jQuery(window).scroll(function(){
	jQuery('.header3 nav').toggleClass('scrolled', jQuery(this).scrollTop() > 5);
});

jQuery(document).ready(function(){

	//Bootstrap Navigation Active ToggleClass
	jQuery( '.navbar-nav a' ).on( 'click', function (event) {

		jQuery( '.navbar-nav' ).find( 'li.active' ).removeClass( 'active' );
		jQuery( this ).parent( 'li' ).addClass( 'active' );

	});


});
