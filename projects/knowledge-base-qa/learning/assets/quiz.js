/* 可复用测验组件。用法：
   <div class="quiz" data-answer="b">
     <p class="q">题干</p>
     <button class="quiz-option" data-key="a">选项 A</button>
     ...
     <p class="feedback" data-correct="..." data-wrong="..."></p>
   </div>
   反馈在点击后立即出现（紧反馈环）；答对答错都会禁用选项。 */
document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll(".quiz").forEach(function (quiz) {
    var answer = quiz.getAttribute("data-answer");
    var feedback = quiz.querySelector(".feedback");
    var options = quiz.querySelectorAll(".quiz-option");

    options.forEach(function (btn) {
      btn.addEventListener("click", function () {
        var picked = btn.getAttribute("data-key");
        var ok = picked === answer;

        options.forEach(function (o) {
          o.disabled = true;
          if (o.getAttribute("data-key") === answer) o.classList.add("correct");
        });
        if (!ok) btn.classList.add("wrong");

        if (feedback) {
          var msg = ok
            ? feedback.getAttribute("data-correct")
            : feedback.getAttribute("data-wrong");
          feedback.textContent = msg || "";
          feedback.classList.add("show");
        }
      });
    });
  });
});
