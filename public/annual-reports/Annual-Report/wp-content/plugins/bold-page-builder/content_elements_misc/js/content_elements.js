(function( $ ) { 
	"use strict";
	// animations
	function bt_bb_animate_elements() {
		var $elems = $( '.animate:not(.animated)' );
		$elems.each(function() {
			var $elm = $( this );
			if ( isOnScreen( $elm ) ) {
				$elm.addClass( 'animated' );
				if ( $elm.hasClass( 'bt_bb_counter' ) ) {
					bt_bb_animate_counter( $elm );
				}
			}
		});
		$( '.slick-slider .slick-slide:not(.slick-active) .animate' ).removeClass( 'animated' );
	}
	
	function isOnScreen( elem ) {
		var element = elem.get( 0 );
		if ( element == undefined ) return false;
		var bounds = element.getBoundingClientRect();
		return bounds.top + 75 < window.innerHeight && bounds.bottom > 0;
	}


	// animate counter
	function bt_bb_animate_counter( elm ) {
		var number_length = elm.data( 'digit-length' );
		for ( var i = parseInt( number_length ); i > 0; i-- ) {
			var digit = parseInt( elm.children( '.p' + i ).data( 'digit' ) );
			if ( digit == 0 || isNaN( digit ) ) digit = 10;
			for ( var j = 0; j <= digit; j++ ) {
				elm.children( '.p' + i ).css( 'transform', 'translateY(-' + digit * elm[0].getBoundingClientRect().height + 'px)' );
			}
			elm.addClass( 'animated' );
		}
		
		return false;
	}
	
	// paralax helpers 
	
	window.bt_bb_requestAnimFrame = function() {
		return (
			window.requestAnimationFrame       ||
			window.webkitRequestAnimationFrame ||
			window.mozRequestAnimationFrame    ||
			window.oRequestAnimationFrame      ||
			window.msRequestAnimationFrame     ||
			function( callback ) {
				window.setTimeout( callback, 1000 / 60 );
			}
		);
	}();

	window.bt_bb_raf_loop = function() {
		var win_w = window.innerWidth;
		var win_h = window.innerHeight;
		$( '.bt_bb_parallax' ).each(function() {
			var bounds = this.getBoundingClientRect();
			if ( bounds.top < win_h && bounds.bottom > 0 ) {
				var speed = $( this ).data( 'parallax' ) + 0.0001;
				var offset = 0;
				if ( win_w > 1024 ) offset = parseFloat( $( this ).data( 'parallax-offset' ) );
				var ypos = ( bounds.top ) * speed;
				$( this )[0].style.backgroundPosition = '50% ' + ( ypos + offset ) + 'px';
			}

		});

		window.bt_bb_raf_lock = false;

	}
	
	// countdown timer helpers
	
	window.bt_bb_countdown = function( elem, selector, i, arr, arr_prev ) {
		
		if ( arr[ i ] !== arr_prev[ i ] || elem.find( selector ).children().eq( 0 ).html( ) == '' ) {
			elem.find( selector ).children().addClass( 'countdown_anim' );
			elem.find( selector ).children().eq( 0 ).html( arr[ i ] );
			elem.find( selector ).children().eq( 1 ).html( arr_prev[ i ] );
			setTimeout(function() {
				elem.find( selector ).children().eq( 1 ).html( elem.find( selector ).children().eq( 0 ).html() );
				elem.find( selector ).children().removeClass( 'countdown_anim' );
			}, 300 );
		}
	}
	
	window.bt_bb_countdown_output = function( elem ) {
		
		var s = elem.data( 'init-seconds' );
		
		var delta = s;
		
		var days = Math.floor( delta / 86400 );
		delta -= days * 86400;

		var hours = Math.floor( delta / 3600 ) % 24;
		delta -= hours * 3600;

		var minutes = Math.floor( delta / 60 ) % 60;
		delta -= minutes * 60;

		var seconds = delta;
		
		if ( hours < 10 ) {
			hours = '0' + hours;
		}
		
		if ( minutes < 10 ) {
			minutes = '0' + minutes;
		}

		if ( seconds < 10 ) {
			seconds = '0' + seconds;
		}
		
		var seconds_arr_prev = seconds.toString().split( '' );
		var minutes_arr_prev = minutes.toString().split( '' );
		var hours_arr_prev = hours.toString().split( '' );		
		
		s = s - 1;
		if ( s < 0 ) {
			s = 0;
		}
		
		var delta = s;
		
		var days = Math.floor( delta / 86400 );
		delta -= days * 86400;

		var hours = Math.floor( delta / 3600 ) % 24;
		delta -= hours * 3600;

		var minutes = Math.floor( delta / 60 ) % 60;
		delta -= minutes * 60;

		var seconds = delta;
		
		if ( hours < 10 ) {
			hours = '0' + hours;
		}
		
		if ( minutes < 10 ) {
			minutes = '0' + minutes;
		}

		if ( seconds < 10 ) {
			seconds = '0' + seconds;
		}
		
		var seconds_arr = seconds.toString().split( '' );
		var minutes_arr = minutes.toString().split( '' );
		var hours_arr = hours.toString().split( '' );
		
		for ( var i = 0; i <= 1; i++ ) {
			bt_bb_countdown( elem, '.seconds .n' + i, i, seconds_arr, seconds_arr_prev );
			bt_bb_countdown( elem, '.minutes .n' + i, i, minutes_arr, minutes_arr_prev );
			bt_bb_countdown( elem, '.hours .n' + i, i, hours_arr, hours_arr_prev );
		}
		
		var days_prev = 0;
		
		if ( days != days_prev ) {
			var days_arr = days.toString().split( '' );
			
			var days_html = '';
			for ( var i = 0; i < days_arr.length; i++ ) {
				days_html += '<span>' + days_arr[ i ] + '</span>';
			}

			elem.find( '.days' ).html( days_html + '<span class="days_text"><span>' + elem.find( '.days' ).data( 'text' ) + '</span></span>' );
		}
		
		days_prev = days;

		elem.data( 'init-seconds', s );		

	}
	
	function bt_bb_fix_slider_heights(){
		$( '.bt_bb_content_slider.bt_bb_height_keep-height .slick-slider' ).each(function( index ) {
			$( this ).find('.slick-slide').height('auto');
			var slickTrack = $( this ).find('.slick-track');
			var slickTrackHeight = $(slickTrack).height();
			$( this ).find('.slick-slide').css('height', slickTrackHeight + 'px');
		});
	}

	function bt_bb_init_elements() {
		
		// get row structure
		
		$( '.bt_bb_section .bt_bb_row' ).each( function( index ) {
			var data_structure = [];
			$( this ).data( 'structure', "0" );
			$( this ).find('.bt_bb_column').each( function( index ) {
				data_structure.push( $( this ).data( 'width' ) );
			});
			$( this ).attr( 'data-structure', data_structure.join("-") );
		});
		
		$( '.bt_bb_row_inner' ).each( function( index ) {
			var data_structure = [];
			$( this ).data( 'structure', "0" );
			$( this ).find('.bt_bb_column_inner').each( function( index ) {
				data_structure.push( $( this ).data( 'width' ) );
			});
			$( this ).attr( 'data-structure', data_structure.join("-") );
		});
		
		
		// slick slider
		$( '.slick-slider' ).slick();
		$( '.slick-slider .slick-prev, .slick-slider .slick-next, .slick-slider .slick-dots li' ).click(function() {
			$( this ).closest( '.slick-slider' ).slick( 'slickPause' );
		});

		// force slider item equal height when keep height is active

		$('.bt_bb_content_slider.bt_bb_height_keep-height .slick-slider').on('setPosition', function () {
			bt_bb_fix_slider_heights();
		});
		$(window).on('resize', function(e) {
			bt_bb_fix_slider_heights();
		});
		 	
		// bt_bb_elements.js resets animated class
		$( '.slick-slider' ).on('beforeChange', function(event, slick, currentSlide, nextSlide){
		  $( this ).find( '.slick-slide .animated' ).removeClass( 'animated' );
		  $( this ).find( '.slick-slide[data-slick-index='+nextSlide+'] .animate' ).addClass( 'animated' );
		});

		// tabs
		$( '.bt_bb_tabs .bt_bb_tabs_header li' ).click(function() {
			$( this ).siblings().removeClass( 'on' );
			$( this ).addClass( 'on' );
			$( this ).closest( '.bt_bb_tabs' ).find( '.bt_bb_tab_item' ).removeClass( 'on' );
			$( this ).closest( '.bt_bb_tabs' ).find( '.bt_bb_tab_item' ).eq( $( this ).index() ).addClass( 'on' );
			

		});
		$( '.bt_bb_tabs' ).each(function() {
			$( this ).find( 'li' ).first().click();
		});

		// parallax
		if ( $( '.bt_bb_parallax' ).length > 0 ) {

			window.bt_bb_raf_lock = false;

			$( window ).on( 'mousewheel', function( e ) {

			});
			
			$( window ).on( 'scroll', function() {
				if ( ! window.bt_bb_raf_lock ) {
					window.bt_bb_raf_lock = true;
					bt_bb_requestAnimFrame( bt_bb_raf_loop );
				}
			});
			
			bt_bb_requestAnimFrame( bt_bb_raf_loop );

			$( window ).on( "load", function() { 
				bt_bb_requestAnimFrame( bt_bb_raf_loop );
			});

		}

		// Countdown
		
		$( '.btCountdownHolder' ).each(function() {

			var cd = $( this );
			var s = cd.data( 'init-seconds' );

			bt_bb_countdown_output( cd );

			setInterval(function() {
				bt_bb_countdown_output( cd );
			}, 1000 );
		});		
	}

	// google maps

	window.bt_bb_gmap_init = function ( map_id, zoom, custom_style ) {

		var myLatLng = new google.maps.LatLng( 0, 0 );
		var mapOptions = {
			zoom: zoom,
			center: myLatLng,
			scrollwheel: false,
			scaleControl:true,
			zoomControl: true,
			zoomControlOptions: {
				style: google.maps.ZoomControlStyle.SMALL,
				position: google.maps.ControlPosition.RIGHT_CENTER
			},
			streetViewControl: true,
			mapTypeControl: true
		}
		var map = new google.maps.Map( document.getElementById( map_id ), mapOptions );

		if ( custom_style != '' ) {
			
			var style_array = [];
			
			if ( custom_style != '' ) {
				style_array = JSON.parse( atob( custom_style ) );
			}
			
			var customMapType = new google.maps.StyledMapType( style_array, {
				name: 'Custom Style'
			});

			var customMapTypeId = 'custom_style';
			map.mapTypes.set( customMapTypeId, customMapType );
			map.setMapTypeId( customMapTypeId );
		}

		var n = 0;

		var container = jQuery( '#' + map_id ).parent();
		
		var locations = container.find( '.bt_bb_google_maps_location' );
		
		var center_map = container.data( 'center' );
		if ( center_map == 'no' ) {
			center_map = false;
		} else {
			center_map = true;
		}

		var lat_sum = 0;
		var lng_sum = 0;
		
		locations.each(function() {
			
			var lat = jQuery( this ).data( 'lat' );
			var lng = jQuery( this ).data( 'lng' );
			var icon = jQuery( this ).data( 'icon' );

			lat_sum += lat;
			lng_sum += lng;

			var myLatLng = new google.maps.LatLng( lat, lng );
			var marker = new google.maps.Marker({
				position: myLatLng,
				map: map,
				icon: icon,
				count: n
			});
			
			if ( ! center_map && n == 0 ) {
				map.setCenter( myLatLng );
			}
			
			locations.eq( 0 ).addClass( 'bt_bb_google_maps_location_show' );
			
			marker.addListener( 'click', function() {
				//map.setZoom( zoom );
				//map.setCenter( marker.getPosition() );
				var reload = true;
				if ( locations.eq( this.count ).hasClass( 'bt_bb_google_maps_location_show' ) && !container.hasClass( 'bt_bb_google_maps_no_overlay' ) ) reload = false; 
				container.removeClass( 'bt_bb_google_maps_no_overlay' );
				locations.removeClass( 'bt_bb_google_maps_location_show' );
				if ( reload ) locations.eq( this.count ).addClass( 'bt_bb_google_maps_location_show' );
			});
			
			n++;
		});

		if ( center_map ) {
			var centerLatLng = new google.maps.LatLng( lat_sum / n, lng_sum / n );
			map.setCenter( centerLatLng );
		}
		
	}
	
	var bt_bb_init_finished = false;
	
	document.addEventListener('readystatechange', function() { 
		if ( ! bt_bb_init_finished && ( document.readyState === 'interactive' || document.readyState === 'complete' ) ) {
			bt_bb_init_elements();
			bt_bb_animate_elements();
			$( window ).on( 'scroll', function() { 
				bt_bb_animate_elements(); 
			});
			$( window ).on( 'resize', function( e ) {		
				setTimeout( function() {
					var $elems = $( '.bt_bb_counter.animated' );
					$elems.each(function() {
						$elm = $( this );
						$elm.removeClass( 'animated' );
						bt_bb_animate_counter( $elm );
					});
				}, 1000 );		
			});
			bt_bb_init_finished = true;		
		}

	}, false);

	

}( jQuery ));