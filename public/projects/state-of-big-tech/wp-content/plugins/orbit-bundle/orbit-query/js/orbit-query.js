// CALLBACK FUNCTION AFTER THE DOM HAS BEEN LOADED
jQuery('document').ready(function(){

	jQuery.fn.ajax_loading_list = function() {
		return this.each(function() {

			var $ul = jQuery( this );

			// GET THE PAGE INCREMENT VALUE AND INCREMENT IT BY 1
			function page_inc() {
				var page = $ul.attr( 'data-page' ) ? parseInt( $ul.attr( 'data-page' ) ) : 1;
				page += 1;
				$ul.attr( 'data-page', page );
				return page;
			};

			// SANITIZE THE URL WITH PAGE INCREMENT VALUE
			function sanitize_url() {
        var url = $ul.attr('data-url') ? $ul.attr('data-url') : location.href,
					hash_index = url.indexOf('#');

				if (hash_index > 0) {
          url = url.substring(0, hash_index);
        }

        url = encodeURI(url);

				/* add page parameter to the request */
        var page = page_inc();

        var paged_attr = $ul.attr('data-paged-attr') ? $ul.attr('data-paged-attr') : 'paged';

        url += (url.split('?')[1] ? '&' : '?') + paged_attr + '=' + page;
        return url;
      };

			// APPEND CHILDREN TO THE LIST USING THE LIST ITEM SELECTORS
			function append_children( result ) {

				if ( jQuery( result ).find( $ul.attr( 'data-target' ) ).length ) {

					$ul.attr( 'data-load-flag', '' );
					jQuery( result ).find( $ul.attr( 'data-target' ) ).each( function() {
						var $list = jQuery(this);
						$list.hide();
						$list.appendTo( $ul );
						$list.show('slow');
						$list.trigger( 'sjax:init', [$list] );
					});
					$ul.trigger( 'ajax-load:complete' );

				} else {
					$ul.trigger( 'ajax-load:no-more' );
				}
			};

			// AJAX REQUEST
			function ajax(){

				$ul.attr( 'data-load-flag', 'ajax' );

				jQuery.ajax({
					'url': sanitize_url(),
					'success': function( result ) {
						$ul.trigger( 'ajax-load:response' );
						append_children( result );
					},
					'error': function() {
						$ul.trigger( 'ajax-load:error' );
					}
				});
			};

			$ul.on( 'ajax-load:start', function( ev ){
				ajax();
			} );

		});
	};

	/* Lazy Loading of the List AT THE TRIGGER OF A BUTTON */
  jQuery.fn.ajax_loading = function() {
		return this.each(function() {

			var $btn 			= jQuery( this ),
				paged_attr 	= $btn.attr( 'data-paged-attr' ) ? $btn.attr( 'data-paged-attr' ) : 'paged',
				$ul 				= jQuery( $btn.data( 'list' ) );

			$ul.attr( 'data-paged-attr', paged_attr );

			$ul.ajax_loading_list();

			// Trigger load more on click
			$btn.click( function( ev ) {
				$btn.data( 'html', $btn.html() );
				$btn.html( 'Loading ...' );
				$ul.trigger( 'ajax-load:start' );
			});

			$ul.on( 'ajax-load:complete', function( ev ){
				$btn.html( $btn.data('html') );
			} );

			$ul.on( 'ajax-load:no-more', function( ev ){
				$btn.hide();
			} );

			$ul.on( 'ajax-load:error', function( ev ){
				$btn.hide();
			} );

		});
  };
  jQuery('body').find("[data-behaviour~=oq-ajax-loading]").ajax_loading();

	jQuery.fn.orbit_lazy_loading = function() {
		return this.each(function() {
			console.log( 'hi' );
			var $el 				= jQuery( this ),
				offset				= $el.data( 'offset' ) ? $el.data( 'offset' ) : 60,
				loading_flag	= false,
				$ul 					= jQuery( $el.data( 'list' ) );

			$ul.ajax_loading_list();

			// Trigger load more on scroll

			jQuery(window).scroll(function() {

				var window_position = jQuery(this).scrollTop() + parseInt( jQuery(window).height() );

				var bottom = $el.offset().top + parseInt( $el.height() ) - offset;

				// Test if the load button has reached
				if( window_position > bottom && !loading_flag ){
					// console.log( bottom );

					$ul.trigger( 'ajax-load:start' );
					loading_flag = true;
				}

			});
			// Trigger load more on scroll ends
			//
			$ul.on( 'ajax-load:complete', function( ev ){
				loading_flag = false;
			} );

			$ul.on( 'ajax-load:no-more', function( ev ){
				$el.remove();
			} );

			$ul.on( 'ajax-load:error', function( ev ){
				$el.remove();
			} );

		});
	};
	jQuery('body').find("[data-behaviour~=orbit-lazy-loading]").orbit_lazy_loading();

	jQuery.fn.reload_html = function(){
  	return this.each(function(){

			var el = jQuery(this);

      jQuery.ajax({
    		url : el.attr('data-url'),
        success : function(result){
        	//console.log(result);
        	//console.log('reload html');
					el.html(result);
					el.find("[data-behaviour~=oq-ajax-loading]").ajax_loading();
        },
        error : function(){
        	el.hide();
        }
      });
		});
  };
  jQuery('body').find("[data-behaviour~=oq-reload-html]").reload_html();

});
