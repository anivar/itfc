jQuery( '[data-behaviour=sp-odometer]' ).each( function(){
  var $odometer = jQuery( this );
  var $odometer_id = $odometer.attr('id')
  var $delay = $odometer.data('delay');

  // Odometer Animation Script
  var a = 0;
  jQuery(window).scroll(function() {

    var oTop = jQuery('#'+ $odometer_id).offset().top - window.innerHeight;
    if (a == 0 && jQuery(window).scrollTop() > oTop) {
      jQuery('.odometer-value').each(function() {
        var $this = jQuery(this),
          countTo = $this.attr('data-count');
          console.log('hiiii');
        jQuery({
          countNum: $this.text()
        }).animate({
            countNum: countTo
          },

          {

            duration: $delay,
            easing: 'swing',
            step: function() {
              $this.text(Math.floor(this.countNum));
            },
            complete: function() {
              $this.text(this.countNum);
              //alert('finished');
            }

          });
      });
      a = 1;
    }

  });

});
