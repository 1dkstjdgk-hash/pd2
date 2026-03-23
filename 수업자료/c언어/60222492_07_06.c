#include <stdio.h>
void main(){
	double num1,num2;
	char e;
	printf("<피연산자1 연산자 피연산자2> 순으로 수식을 입력하시오:");
	scanf("%lf %c %lf",&num1,&e,&num2);
	switch(e){
		case'+': printf("연산결과:%lf",num1+num2);
	    break;
	    case'-': printf("연산결과:%lf",num1-num2);
	    break;
	    case'*': printf("연산결과:%lf",num1*num2);
	    break;
	    case'/': printf("연산결과:%lf",num1/num2);
	    break;
	    default: printf("처리할 수 없는 연산자가 입력되었습니다.\n");
	             printf("연산결과가 없습니다.");
	}
	
}
