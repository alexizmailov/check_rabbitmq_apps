<?php
$num = 0;
$app_prev='';

foreach($NAME as $line)
{
  $title = explode('_', $line);
  unset($title[count($title)-1]);
  $app = implode("_",$title);

  if ($app_prev != $app)
  {
    $num+=1;
    $app_prev = $app;
    $opt[$num] = '--vertical-label "messages"  --title "'. $app .'" -l 0 ';
    $STACK=true;
    $FILL=true;
    $REGEX='/'. $app .'_/';
    if ($num > 12)
      $START_COLOR=$num - 11;
    else
      $START_COLOR=$num;
    require('stack_outline.php');
  }
}

?>

