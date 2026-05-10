jQuery.fn.youtube_video_thumb = function() {

	return this.each(function() {

		var $el = jQuery(this);

    // CREATES DYNAMIC VIDEO MODAL
		$el.on( 'click', function() {
      var youtube_api = 'https://www.youtube.com/embed/';
      youtube_api += jQuery($el).data('url');
      youtube_api += '?&autoplay=1';
      $el.createModal(youtube_api);
		});

    // VIDEO MODAL LAYOUT
    $el.createModal = function(embed_url) {
      html =  '<div id="sp-youtube-modal" class="sp-youtube-popup modal fade" tabindex="-1" role="dialog">';
      html += '<div class="modal-dialog">';
      html += '<div class="modal-content">';
      html += '<div class="modal-body text-center">';
      html += '<iframe width="100%" height="100%" allow="autoplay" src="';
      html += embed_url;
      html += '"></iframe>'
      html += '</div>';   // body
      html += '</div>';   // content
      html += '</div>';  // dialog
      html += '</div>';  // modalWindow
      jQuery("body").append(html).modal();
    }

    // REMOVES MODAL FROM THE DOM
    jQuery(document).on('hidden.bs.modal', function () {
      jQuery('#sp-youtube-modal').remove();
      jQuery('.modal-backdrop.in').remove();
    });

	}); //End each()

};

jQuery(document).ready(function () {

	jQuery('a[data-behaviour~=sp-youtube]').youtube_video_thumb(); /* EXECUTED ONLY ONCE */

	/* EXECUTED ONLY WHEN THE BODY IS CHANGED */
	jQuery("body").on('change',function(){
		jQuery('a[data-behaviour~=sp-youtube]').youtube_video_thumb();
	});

});
